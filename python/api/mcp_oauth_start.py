import base64
import hashlib
import hmac
import json
import os
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response


class McpOauthStart(ApiHandler):
    """Initiate OAuth flow for an MCP service.

    Returns an authorization URL that the frontend opens in a popup window.
    The state parameter encodes user_id and service_id for the callback.
    """

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("mcp", "write")

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        user_id = self._get_user_id()
        service_id = input.get("service_id")

        if not user_id:
            return Response(
                json.dumps({"error": "Authentication required"}),
                status=401,
                mimetype="application/json",
            )

        if not service_id:
            return Response(
                json.dumps({"error": "service_id is required"}),
                status=400,
                mimetype="application/json",
            )

        with auth_db.get_session() as db:
            service = user_store.get_service(db, service_id)
            if not service:
                return Response(
                    json.dumps({"error": "Service not found"}),
                    status=404,
                    mimetype="application/json",
                )

            if service.transport_type != "streamable_http":
                return Response(
                    json.dumps({"error": "OAuth is only for streamable_http services"}),
                    status=400,
                    mimetype="application/json",
                )

            # Build the OAuth authorization URL with state
            app_base_url = os.environ.get("APP_BASE_URL", "http://localhost:50080")
            callback_url = f"{app_base_url}/mcp/oauth/callback"

            state_data = {
                "user_id": user_id,
                "service_id": service_id,
                "scopes": service.default_scopes or "",
            }
            payload = base64.b64encode(json.dumps(state_data).encode()).decode()
            from flask import current_app

            secret_key = (
                current_app.secret_key.encode()
                if isinstance(current_app.secret_key, str)
                else current_app.secret_key
            )
            signature = hmac.new(
                secret_key, payload.encode(), hashlib.sha256
            ).hexdigest()
            state = f"{payload}.{signature}"

            # Build authorization URL components
            # The actual OAuth discovery and PKCE is handled by the MCP SDK's
            # OAuthClientProvider when connecting. This endpoint provides the
            # metadata needed for the frontend to initiate the flow.
            return {
                "ok": True,
                "data": {
                    "service_id": service_id,
                    "service_name": service.name,
                    "server_url": service.server_url,
                    "client_id": service.client_id,
                    "scopes": service.default_scopes or "",
                    "callback_url": callback_url,
                    "state": state,
                },
            }
