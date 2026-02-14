import contextvars
import os
import threading
import time
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

import fastmcp
from fastmcp import FastMCP
from fastmcp.server.auth import AuthContext
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.http import (  # type: ignore
    build_resource_metadata_url,
    create_base_app,
    create_sse_app,
)
from openai import BaseModel
from pydantic import Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Mount  # type: ignore
from starlette.types import ASGIApp, Receive, Scope, Send

from agent import AgentContext, AgentContextType, UserMessage
from initialize import initialize_agent
from python.helpers import branding, projects, settings
from python.helpers.mcp_gateway_compositor import McpGatewayCompositor
from python.helpers.persist_chat import remove_chat
from python.helpers.print_style import PrintStyle

_PRINTER = PrintStyle(italic=True, font_color="green", padding=False)

# Context variable to store project name from URL (per-request)
_mcp_project_name: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_project_name", default=None
)

# ---------------------------------------------------------------------------
# MCP Azure auth configuration
# ---------------------------------------------------------------------------

_azure_auth_configured: bool = False


def _parse_redirect_uris() -> list[str] | None:
    """Parse comma-separated redirect URIs from env."""
    raw = os.environ.get("MCP_AZURE_REDIRECT_URIS", "")
    if not raw.strip():
        return None
    return [u.strip() for u in raw.split(",") if u.strip()]


def configure_mcp_auth() -> None:
    """Conditionally attach AzureProvider to the MCP server.

    Reads ``MCP_AZURE_CLIENT_ID``, ``MCP_AZURE_CLIENT_SECRET``, and
    ``MCP_AZURE_TENANT_ID`` from the environment.  If all three are present,
    creates an :class:`AzureProvider` and assigns it to ``mcp_server.auth``.
    Otherwise, ``mcp_server.auth`` stays ``None`` and token-in-path
    authentication continues working as-is.
    """
    global _azure_auth_configured  # noqa: PLW0603

    client_id = os.environ.get("MCP_AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("MCP_AZURE_CLIENT_SECRET", "")
    tenant_id = os.environ.get("MCP_AZURE_TENANT_ID", "")

    if not (client_id and client_secret and tenant_id):
        _PRINTER.print("[MCP] Azure auth not configured — token-in-path only")
        return

    from fastmcp.server.auth.providers.azure import AzureProvider

    identifier_uri = os.environ.get("MCP_AZURE_IDENTIFIER_URI") or f"api://{client_id}"
    base_url = os.environ.get("MCP_SERVER_BASE_URL", "http://localhost:50080")

    auth = AzureProvider(
        client_id=client_id,
        client_secret=client_secret,
        tenant_id=tenant_id,
        base_url=base_url,
        identifier_uri=identifier_uri,
        required_scopes=["discover", "tools.read", "tools.execute", "chat"],
        allowed_client_redirect_uris=_parse_redirect_uris(),
        jwt_signing_key=os.environ.get("MCP_AZURE_JWT_SIGNING_KEY"),
    )
    mcp_server.auth = auth
    _azure_auth_configured = True
    PrintStyle.step("MCP OAuth", "AzureProvider configured")


# ---------------------------------------------------------------------------
# Per-tool scope enforcement (coexists with token-in-path)
# ---------------------------------------------------------------------------


def require_scopes_or_token_path(*scopes: str):
    """Allow access if Bearer token has scopes OR if using token-in-path auth.

    When ``mcp_server.auth`` is configured, requests arriving via the
    token-in-path route will NOT carry a Bearer token.  In that case we
    allow access unconditionally (the token already proved authorization).
    For Bearer-authenticated requests we enforce the given scopes.
    """

    def check(ctx: AuthContext) -> bool:
        if ctx.token is None:
            return True  # token-in-path mode — no scope enforcement
        return all(s in ctx.token.scopes for s in scopes)

    return check


# ---------------------------------------------------------------------------
# User identity helpers
# ---------------------------------------------------------------------------


async def _get_mcp_user() -> dict | None:
    """Get authenticated MCP user from Bearer token claims.

    Returns ``None`` when the request is using token-in-path auth
    (no Bearer token present).
    """
    token = get_access_token()
    if token is None:
        return None
    return {
        "id": token.claims.get("oid"),
        "email": token.claims.get("preferred_username"),
        "name": token.claims.get("name"),
        "scopes": list(token.scopes),
        "client_id": token.client_id,
    }


# ---------------------------------------------------------------------------
# RBAC auth check for MCP requests
# ---------------------------------------------------------------------------


def require_rbac_mcp_access(ctx: AuthContext) -> bool:
    """Custom auth check: verify Casbin allows MCP access for this user.

    Passes unconditionally for token-in-path requests (no Bearer token).
    For Bearer-authenticated requests, looks up the user in the auth DB
    and checks Casbin RBAC policies.
    """
    if ctx.token is None:
        return True  # token-in-path mode

    user_id = ctx.token.claims.get("oid")
    if not user_id:
        return False

    try:
        from python.helpers import auth_db, user_store
        from python.helpers.rbac import get_enforcer

        with auth_db.get_session() as db:
            user = user_store.get_user_by_id(db, user_id)
            if not user:
                return False
            org_id = user.primary_org_id or "*"
            # Find first team membership for domain construction
            team_id = "*"
            if user.team_memberships:
                team_id = user.team_memberships[0].team_id
            domain = f"org:{org_id}/team:{team_id}"
            return get_enforcer().enforce(user_id, domain, "mcp", "execute")
    except Exception as e:
        _PRINTER.print(f"[MCP] RBAC check failed: {e}")
        return False


# ---------------------------------------------------------------------------
# MCP rate limiting (per-user, in-memory)
# ---------------------------------------------------------------------------

_mcp_rate_limits: dict[str, list[float]] = {}
_MCP_RATE_LIMIT = 100  # requests per minute
_MCP_RATE_WINDOW = 60  # seconds


def _check_mcp_rate_limit(user_id: str) -> bool:
    """Return True if the user is within rate limits, False if exceeded."""
    now = time.monotonic()
    cutoff = now - _MCP_RATE_WINDOW
    attempts = _mcp_rate_limits.get(user_id, [])
    attempts = [t for t in attempts if t > cutoff]
    attempts.append(now)
    _mcp_rate_limits[user_id] = attempts
    return len(attempts) <= _MCP_RATE_LIMIT


# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

mcp_server: FastMCP = FastMCP(
    name=f"{branding.BRAND_NAME} integrated MCP Server",
    instructions=f"""
    Connect to remote {branding.BRAND_NAME} instance.
    {branding.BRAND_NAME} is a general AI assistant controlling it's linux environment.
    {branding.BRAND_NAME} can install software, manage files, execute commands, code, use internet, etc.
    {branding.BRAND_NAME}'s environment is isolated unless configured otherwise.
    """,
)

# Configure Azure auth if env vars are set (must happen after mcp_server creation)
configure_mcp_auth()


class ToolResponse(BaseModel):
    status: Literal["success"] = Field(
        description="The status of the response", default="success"
    )
    response: str = Field(
        description=f"The response from the remote {branding.BRAND_NAME} Instance"
    )
    chat_id: str = Field(description="The id of the chat this message belongs to.")


class ToolError(BaseModel):
    status: Literal["error"] = Field(
        description="The status of the response", default="error"
    )
    error: str = Field(
        description=f"The error message from the remote {branding.BRAND_NAME} Instance"
    )
    chat_id: str = Field(description="The id of the chat this message belongs to.")


SEND_MESSAGE_DESCRIPTION = f"""
Send a message to the remote {branding.BRAND_NAME} Instance.
This tool is used to send a message to the remote {branding.BRAND_NAME} Instance connected remotely via MCP.
"""


@mcp_server.tool(
    name="send_message",
    description=SEND_MESSAGE_DESCRIPTION,
    tags={
        "agent_zero",
        "chat",
        "remote",
        "communication",
        "dialogue",
        "sse",
        "send",
        "message",
        "start",
        "new",
        "continue",
    },
    annotations={
        "remote": True,
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
        "title": SEND_MESSAGE_DESCRIPTION,
    },
    auth=require_scopes_or_token_path("chat"),
)
async def send_message(
    message: Annotated[
        str,
        Field(
            description=f"The message to send to the remote {branding.BRAND_NAME} Instance",
            title="message",
        ),
    ],
    attachments: (
        Annotated[
            list[str],
            Field(
                description=f"Optional: A list of attachments (file paths or web urls) to send to the remote {branding.BRAND_NAME} Instance with the message. Default: Empty list",
                title="attachments",
            ),
        ]
        | None
    ) = None,
    chat_id: (
        Annotated[
            str,
            Field(
                description="Optional: ID of the chat. Used to continue a chat. This value is returned in response to sending previous message. Default: Empty string",
                title="chat_id",
            ),
        ]
        | None
    ) = None,
    persistent_chat: (
        Annotated[
            bool,
            Field(
                description="Optional: Whether to use a persistent chat. If true, the chat will be saved and can be continued later. Default: False.",
                title="persistent_chat",
            ),
        ]
        | None
    ) = None,
) -> Annotated[
    Union[ToolResponse, ToolError],
    Field(
        description=f"The response from the remote {branding.BRAND_NAME} Instance",
        title="response",
    ),
]:
    # Get project name from context variable (set in proxy __call__)
    project_name = _mcp_project_name.get()

    # Get authenticated user identity (None for token-in-path)
    mcp_user = await _get_mcp_user()

    # Audit log the tool invocation
    try:
        from python.helpers.audit import create_audit_entry

        await create_audit_entry(
            user_id=mcp_user["id"] if mcp_user else None,
            action="mcp_tool_invoke",
            resource="send_message",
            details={"chat_id": chat_id, "project": project_name},
        )
    except Exception:
        pass  # audit is fire-and-forget

    context: AgentContext | None = None
    if chat_id:
        context = AgentContext.get(chat_id)
        if not context:
            return ToolError(error="Chat not found", chat_id=chat_id)
        else:
            # If the chat is found, we use the persistent chat flag to determine
            # whether we should save the chat or delete it afterwards
            # If we continue a conversation, it must be persistent
            persistent_chat = True

            # Validation: if project is in URL but context has different project
            if project_name:
                existing_project = context.get_data(projects.CONTEXT_DATA_KEY_PROJECT)
                if existing_project and existing_project != project_name:
                    return ToolError(
                        error=f"Chat belongs to project '{existing_project}' but URL specifies '{project_name}'",
                        chat_id=chat_id,
                    )
    else:
        config = initialize_agent()
        context = AgentContext(config=config, type=AgentContextType.BACKGROUND)

        # Activate project if specified in URL
        if project_name:
            try:
                projects.activate_project(context.id, project_name)
            except Exception as e:
                return ToolError(
                    error=f"Failed to activate project: {str(e)}", chat_id=""
                )

    if not message:
        return ToolError(
            error="Message is required", chat_id=context.id if persistent_chat else ""
        )

    try:
        response = await _run_chat(context, message, attachments)
        if not persistent_chat:
            context.reset()
            AgentContext.remove(context.id)
            remove_chat(context.id)
        return ToolResponse(
            response=response, chat_id=context.id if persistent_chat else ""
        )
    except Exception as e:
        return ToolError(error=str(e), chat_id=context.id if persistent_chat else "")


FINISH_CHAT_DESCRIPTION = f"""
Finish a chat with the remote {branding.BRAND_NAME} Instance.
This tool is used to finish a persistent chat (send_message with persistent_chat=True) with the remote {branding.BRAND_NAME} Instance connected remotely via MCP.
If you want to continue the chat, use the send_message tool instead.
Always use this tool to finish persistent chat conversations with remote {branding.BRAND_NAME}.
"""


@mcp_server.tool(
    name="finish_chat",
    description=FINISH_CHAT_DESCRIPTION,
    tags={
        "agent_zero",
        "chat",
        "remote",
        "communication",
        "dialogue",
        "sse",
        "finish",
        "close",
        "end",
        "stop",
    },
    annotations={
        "remote": True,
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
        "title": FINISH_CHAT_DESCRIPTION,
    },
    auth=require_scopes_or_token_path("chat"),
)
async def finish_chat(
    chat_id: Annotated[
        str,
        Field(
            description="ID of the chat to be finished. This value is returned in response to sending previous message.",
            title="chat_id",
        ),
    ],
) -> Annotated[
    Union[ToolResponse, ToolError],
    Field(
        description=f"The response from the remote {branding.BRAND_NAME} Instance",
        title="response",
    ),
]:
    if not chat_id:
        return ToolError(error="Chat ID is required", chat_id="")

    # Audit log
    try:
        mcp_user = await _get_mcp_user()
        from python.helpers.audit import create_audit_entry

        await create_audit_entry(
            user_id=mcp_user["id"] if mcp_user else None,
            action="mcp_tool_invoke",
            resource="finish_chat",
            details={"chat_id": chat_id},
        )
    except Exception:
        pass

    context = AgentContext.get(chat_id)
    if not context:
        return ToolError(error="Chat not found", chat_id=chat_id)
    else:
        context.reset()
        AgentContext.remove(context.id)
        remove_chat(context.id)
        return ToolResponse(response="Chat finished", chat_id=chat_id)


async def _run_chat(
    context: AgentContext, message: str, attachments: list[str] | None = None
):
    try:
        _PRINTER.print("MCP Chat message received")

        # Attachment filenames for logging
        attachment_filenames = []
        if attachments:
            for attachment in attachments:
                if os.path.exists(attachment):
                    attachment_filenames.append(attachment)
                else:
                    try:
                        url = urlparse(attachment)
                        if url.scheme in ["http", "https", "ftp", "ftps", "sftp"]:
                            attachment_filenames.append(attachment)
                        else:
                            _PRINTER.print(f"Skipping attachment: [{attachment}]")
                    except Exception:
                        _PRINTER.print(f"Skipping attachment: [{attachment}]")

        _PRINTER.print("User message:")
        _PRINTER.print(f"> {message}")
        if attachment_filenames:
            _PRINTER.print("Attachments:")
            for filename in attachment_filenames:
                _PRINTER.print(f"- {filename}")

        task = context.communicate(
            UserMessage(
                message=message, system_message=[], attachments=attachment_filenames
            )
        )
        result = await task.result()

        # Success
        _PRINTER.print(f"MCP Chat message completed: {result}")

        return result

    except Exception as e:
        # Error
        _PRINTER.print(f"MCP Chat message failed: {e}")

        raise RuntimeError(f"MCP Chat message failed: {e}") from e


class DynamicMcpProxy:
    _instance: "DynamicMcpProxy | None" = None

    """A dynamic proxy that allows swapping the underlying MCP applications on the fly."""

    def __init__(self):
        cfg = settings.get_settings()
        self.token = ""
        self.sse_app: ASGIApp | None = None
        self.http_app: ASGIApp | None = None
        self.http_session_manager = None
        self.http_session_task_group = None
        self._lock = threading.RLock()  # Use RLock to avoid deadlocks
        self.compositor = McpGatewayCompositor(mcp_server)
        self.reconfigure(cfg["mcp_server_token"])

    @staticmethod
    def get_instance():
        if DynamicMcpProxy._instance is None:
            DynamicMcpProxy._instance = DynamicMcpProxy()
        return DynamicMcpProxy._instance

    def reconfigure(self, token: str):
        if self.token == token:
            return

        self.token = token
        sse_path = f"/t-{self.token}/sse"
        http_path = f"/t-{self.token}/http"
        message_path = f"/t-{self.token}/messages/"

        # Update settings in the MCP server instance if provided
        # Keep FastMCP settings synchronized so downstream helpers that read these
        # values (including deprecated accessors) resolve the runtime paths.
        fastmcp.settings.message_path = message_path
        fastmcp.settings.sse_path = sse_path
        fastmcp.settings.streamable_http_path = http_path

        # Create new MCP apps with updated settings
        with self._lock:
            middleware = [Middleware(BaseHTTPMiddleware, dispatch=mcp_middleware)]

            self.sse_app = create_sse_app(
                server=mcp_server,
                message_path=message_path,
                sse_path=sse_path,
                auth=mcp_server.auth,
                debug=fastmcp.settings.debug,
                middleware=list(middleware),
            )

            self.http_app = self._create_custom_http_app(
                http_path,
                middleware=list(middleware),
            )

    async def refresh_mounts(self) -> None:
        """Re-read the resource store and update gateway mounts.

        Unmounts servers no longer in the store and mounts new ones.
        Safe to call repeatedly — idempotent.
        """
        from python.api.mcp_gateway_servers import get_store

        store = get_store()
        resources = store.list_all()
        resource_names = {r.name for r in resources if r.is_enabled}

        # Unmount servers that are no longer in the store
        for name in list(self.compositor.mounted_names):
            if name not in resource_names:
                await self.compositor.unmount_server(name)

        # Mount servers that are new
        for resource in resources:
            if (
                resource.is_enabled
                and resource.name not in self.compositor.mounted_names
            ):
                try:
                    await self.compositor.mount_server(resource)
                except Exception as e:
                    _PRINTER.print(
                        f"[MCP] Failed to mount gateway server '{resource.name}': {e}"
                    )

    def _create_custom_http_app(
        self,
        streamable_http_path: str,
        *,
        middleware: list[Middleware],
    ) -> ASGIApp:
        """Create a Streamable HTTP app with manual session manager lifecycle."""

        import anyio
        from mcp.server.auth.middleware.bearer_auth import (
            RequireAuthMiddleware,  # type: ignore
        )
        from mcp.server.streamable_http_manager import (
            StreamableHTTPSessionManager,  # type: ignore
        )

        server_routes = []
        server_middleware = []

        self.http_session_task_group = None
        self.http_session_manager = StreamableHTTPSessionManager(
            app=mcp_server._mcp_server,
            event_store=None,
            json_response=True,
            stateless=False,
        )

        async def handle_streamable_http(scope, receive, send):
            if self.http_session_task_group is None:
                self.http_session_task_group = anyio.create_task_group()
                await self.http_session_task_group.__aenter__()
                if self.http_session_manager:
                    self.http_session_manager._task_group = self.http_session_task_group

            if self.http_session_manager:
                await self.http_session_manager.handle_request(scope, receive, send)

        auth_provider = mcp_server.auth

        if auth_provider:
            server_routes.extend(
                auth_provider.get_routes(mcp_path=streamable_http_path)
            )
            server_middleware.extend(auth_provider.get_middleware())

            resource_url = auth_provider._get_resource_url(streamable_http_path)
            resource_metadata_url = (
                build_resource_metadata_url(resource_url) if resource_url else None
            )

            server_routes.append(
                Mount(
                    streamable_http_path,
                    app=RequireAuthMiddleware(
                        handle_streamable_http,
                        auth_provider.required_scopes,
                        resource_metadata_url,
                    ),
                )
            )
        else:
            server_routes.append(
                Mount(
                    streamable_http_path,
                    app=handle_streamable_http,
                )
            )

        additional_routes = mcp_server._get_additional_http_routes()
        if additional_routes:
            server_routes.extend(additional_routes)

        server_middleware.extend(middleware)

        return create_base_app(
            routes=server_routes,
            middleware=server_middleware,
            debug=fastmcp.settings.debug,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Forward the ASGI calls to the appropriate app based on the URL path"""
        with self._lock:
            sse_app = self.sse_app
            http_app = self.http_app

        if not sse_app or not http_app:
            raise RuntimeError("MCP apps not initialized")

        # Route based on path
        path = scope.get("path", "")

        # Check for token in path (with or without project segment)
        # Patterns: /t-{token}/sse, /t-{token}/p-{project}/sse, etc.
        has_token = f"/t-{self.token}/" in path or f"t-{self.token}/" in path

        # Extract project from path BEFORE cleaning and set in context variable
        project_name = None
        if "/p-" in path:
            try:
                parts = path.split("/p-")
                if len(parts) > 1:
                    project_part = parts[1].split("/")[0]
                    if project_part:
                        project_name = project_part
                        _PRINTER.print(
                            f"[MCP] Proxy extracted project from URL: {project_name}"
                        )
            except Exception as e:
                _PRINTER.print(f"[MCP] Failed to extract project in proxy: {e}")

        # Store project in context variable (will be available in send_message)
        _mcp_project_name.set(project_name)

        # Strip project segment from path if present (e.g., /p-project_name/)
        # This is needed because the underlying MCP apps were configured without project paths
        cleaned_path = path
        if "/p-" in path:
            # Remove /p-{project}/ segment: /t-TOKEN/p-PROJECT/sse -> /t-TOKEN/sse
            import re

            cleaned_path = re.sub(r"/p-[^/]+/", "/", path)

        # Update scope with cleaned path for the underlying app
        modified_scope = dict(scope)
        modified_scope["path"] = cleaned_path

        if has_token and ("/sse" in path or "/messages" in path):
            # Route to SSE app with cleaned path
            await sse_app(modified_scope, receive, send)
        elif has_token and "/http" in path:
            # Route to HTTP app with cleaned path
            await http_app(modified_scope, receive, send)
        elif not has_token and mcp_server.auth is not None and "/http" in path:
            # Bearer token fallback: OAuth-authenticated clients connect at
            # /mcp/http without a token-in-path.  Route to http_app which
            # has RequireAuthMiddleware that validates Bearer tokens.
            # Rewrite path so the underlying app finds its expected route.
            bearer_scope = dict(scope)
            bearer_scope["path"] = f"/t-{self.token}/http"
            await http_app(bearer_scope, receive, send)
        elif (
            not has_token
            and mcp_server.auth is not None
            and (path.startswith("/auth/") or path.startswith("/.well-known/"))
        ):
            # OAuth routes (callback, PRM) — pass through to http_app
            bearer_scope = dict(scope)
            await http_app(bearer_scope, receive, send)
        else:
            raise StarletteHTTPException(status_code=403, detail="MCP forbidden")


async def mcp_middleware(request: Request, call_next):
    """Middleware to check if MCP server is enabled and enforce rate limits."""
    # check if MCP server is enabled
    cfg = settings.get_settings()
    if not cfg["mcp_server_enabled"]:
        PrintStyle.error("[MCP] Access denied: MCP server is disabled in settings.")
        raise StarletteHTTPException(
            status_code=403, detail="MCP server is disabled in settings."
        )

    # Per-user rate limiting for Bearer-authenticated requests
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer ") and _azure_auth_configured:
        # Extract user_id from token claims (lightweight check via get_access_token
        # happens later; here we just key by the first 16 chars of token hash)
        import hashlib

        token_key = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
        if not _check_mcp_rate_limit(token_key):
            raise StarletteHTTPException(
                status_code=429,
                detail="Rate limit exceeded. Max 100 requests per minute.",
            )

    return await call_next(request)
