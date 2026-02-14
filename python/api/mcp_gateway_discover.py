"""MCP Gateway discovery API — search and install from MCP Registry.

Proxies to McpRegistryClient for server discovery and converts
registry entries into McpServerResource objects for installation.
"""

import json
import logging
from typing import Any

from python.helpers.api import ApiHandler, Request, Response
from python.helpers.mcp_registry_client import McpRegistryClient
from python.helpers.mcp_resource_store import (
    InMemoryMcpResourceStore,
    McpServerResource,
)

logger = logging.getLogger(__name__)

# Module-level singleton
_registry_client: McpRegistryClient | None = None


def _get_registry_client() -> McpRegistryClient:
    global _registry_client
    if _registry_client is None:
        _registry_client = McpRegistryClient()
    return _registry_client


async def handle_search(
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Search the MCP Registry for servers."""
    try:
        client = _get_registry_client()
        results = await client.search(query, limit=limit)
        return {"ok": True, "data": results}
    except Exception as exc:
        logger.warning("Registry search failed: %s", exc)
        return {"ok": False, "error": str(exc)}


async def handle_install(
    store: InMemoryMcpResourceStore,
    user_id: str,
    server_data: dict[str, Any],
) -> dict[str, Any]:
    """Convert a registry entry to a McpServerResource and add to store."""
    name = server_data.get("name")
    if not name:
        return {"ok": False, "error": "Missing required field: name"}

    packages = server_data.get("packages", [])
    remotes = server_data.get("remotes", [])

    # Infer transport and command from package or remote info
    transport_type = "streamable_http"
    command = ""
    args: list[str] = []
    docker_image = ""
    url = ""

    if packages:
        pkg = packages[0]
        # Support both old format (registry_name/name/version) and
        # new format (registryType/identifier)
        registry = pkg.get("registry_name", "") or pkg.get("registryType", "")
        pkg_name = pkg.get("name", "")
        pkg_version = pkg.get("version", "")
        identifier = pkg.get("identifier", "")
        pkg_transport = pkg.get("transport", {}).get("type", "")

        if not pkg_name and identifier:
            # Parse identifier like "docker.io/user/repo:tag" or "@scope/pkg"
            pkg_name = identifier.split(":")[0] if ":" in identifier else identifier
            pkg_version = (
                identifier.split(":")[-1]
                if ":" in identifier and identifier.split(":")[-1] != pkg_name
                else ""
            )

        if registry in ("npm",):
            transport_type = pkg_transport or "stdio"
            command = "npx"
            version_suffix = f"@{pkg_version}" if pkg_version else ""
            args = ["-y", f"{pkg_name}{version_suffix}"]
        elif registry in ("pip", "pypi"):
            transport_type = pkg_transport or "stdio"
            command = "uvx"
            args = [pkg_name]
        elif registry in ("docker", "oci"):
            transport_type = pkg_transport or "stdio"
            docker_image = identifier or (
                f"{pkg_name}:{pkg_version}" if pkg_version else pkg_name
            )
    elif remotes:
        # Hosted MCP servers with a remote URL
        remote = remotes[0]
        remote_type = remote.get("type", "streamable-http")
        url = remote.get("url", "")
        transport_type = "streamable_http" if "http" in remote_type else remote_type

    resource = McpServerResource(
        name=name,
        transport_type=transport_type,
        created_by=user_id,
        url=url or None,
        command=command,
        args=args,
        docker_image=docker_image or None,
        is_enabled=True,
    )
    store.upsert(resource)

    from python.api.mcp_gateway_servers import resource_to_dict

    return {"ok": True, "data": resource_to_dict(resource)}


class McpGatewayDiscover(ApiHandler):
    """Discovery API for browsing and installing from MCP Registry."""

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return None

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action", "search")
        user_id = self._get_user_id() or "anonymous"

        if action == "search":
            query = input.get("query", "")
            limit = input.get("limit", 20)
            return await handle_search(query=query, limit=limit)

        elif action == "install":
            from python.api.mcp_gateway_servers import get_store

            store = get_store()
            server_data = input.get("server", input)
            return await handle_install(
                store=store, user_id=user_id, server_data=server_data
            )

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
