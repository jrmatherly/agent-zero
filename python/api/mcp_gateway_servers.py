"""MCP Gateway server management API with CRUD and RBAC.

Manages McpServerResource objects through the InMemoryMcpResourceStore.
Follows the action-based dispatch pattern from mcp_services.py.
"""

import json
from typing import Any

from python.helpers.api import ApiHandler, Request, Response
from python.helpers.mcp_resource_store import (
    InMemoryMcpResourceStore,
    McpServerResource,
)

# Module-level store singleton
_store = InMemoryMcpResourceStore()


def get_store() -> InMemoryMcpResourceStore:
    """Return the module-level resource store singleton."""
    return _store


def resource_to_dict(r: McpServerResource) -> dict[str, Any]:
    """Serialize a McpServerResource to a JSON-friendly dict."""
    return {
        "name": r.name,
        "transport_type": r.transport_type,
        "created_by": r.created_by,
        "url": r.url,
        "command": r.command,
        "args": r.args,
        "env": r.env,
        "docker_image": r.docker_image,
        "docker_ports": r.docker_ports,
        "required_roles": r.required_roles,
        "is_enabled": r.is_enabled,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def handle_list(
    store: InMemoryMcpResourceStore,
    user_id: str,
    roles: list[str],
) -> dict[str, Any]:
    """List all resources accessible to the given user."""
    all_resources = store.list_all()
    accessible = [
        resource_to_dict(r)
        for r in all_resources
        if r.can_access(user_id, roles=roles, operation="read")
    ]
    return {"ok": True, "data": accessible}


def handle_create(
    store: InMemoryMcpResourceStore,
    user_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Create a new McpServerResource in the store."""
    name = data.get("name")
    transport_type = data.get("transport_type")

    if not name:
        return {"ok": False, "error": "Missing required field: name"}
    if not transport_type:
        return {"ok": False, "error": "Missing required field: transport_type"}

    resource = McpServerResource(
        name=name,
        transport_type=transport_type,
        created_by=user_id,
        url=data.get("url"),
        command=data.get("command"),
        args=data.get("args", []),
        env=data.get("env", {}),
        docker_image=data.get("docker_image"),
        docker_ports=data.get("docker_ports", {}),
        required_roles=data.get("required_roles", []),
        is_enabled=data.get("is_enabled", True),
    )
    store.upsert(resource)
    return {"ok": True, "data": resource_to_dict(resource)}


def handle_update(
    store: InMemoryMcpResourceStore,
    user_id: str,
    roles: list[str],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Update an existing McpServerResource."""
    name = data.get("name")
    if not name:
        return {"ok": False, "error": "Missing required field: name"}

    existing = store.get(name)
    if existing is None:
        return {"ok": False, "error": f"Resource not found: {name}"}

    if not existing.can_access(user_id, roles=roles, operation="write"):
        return {"ok": False, "error": "Forbidden: insufficient permissions"}

    # Merge updatable fields
    updatable = (
        "url",
        "command",
        "args",
        "env",
        "docker_image",
        "docker_ports",
        "required_roles",
        "is_enabled",
        "transport_type",
    )
    for field in updatable:
        if field in data:
            setattr(existing, field, data[field])

    store.upsert(existing)
    return {"ok": True, "data": resource_to_dict(existing)}


def handle_delete(
    store: InMemoryMcpResourceStore,
    user_id: str,
    roles: list[str],
    name: str,
) -> dict[str, Any]:
    """Delete a McpServerResource from the store."""
    existing = store.get(name)
    if existing is None:
        return {"ok": False, "error": f"Resource not found: {name}"}

    if not existing.can_access(user_id, roles=roles, operation="write"):
        return {"ok": False, "error": "Forbidden: insufficient permissions"}

    store.delete(name)
    return {"ok": True}


def handle_status(
    store: InMemoryMcpResourceStore,
    name: str,
    container_manager: Any = None,
) -> dict[str, Any]:
    """Get status for a gateway server."""
    existing = store.get(name)
    if existing is None:
        return {"ok": False, "error": f"Resource not found: {name}"}

    result: dict[str, Any] = {
        "name": existing.name,
        "transport_type": existing.transport_type,
        "is_enabled": existing.is_enabled,
    }

    # Include container status if manager is available
    if container_manager is not None:
        result["container"] = container_manager.get_status(name)
    else:
        result["container"] = {"running": False, "status": "no_manager"}

    return {"ok": True, "data": result}


class McpGatewayServers(ApiHandler):
    """CRUD API for MCP gateway server resources."""

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        # Dynamic: read is filtered by can_access, write checked in handlers
        return None

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action", "list")
        user_id = self._get_user_id() or "anonymous"
        store = get_store()

        # Determine user roles from session
        try:
            from flask import g

            user = g.current_user if hasattr(g, "current_user") else None
            roles = user.get("roles", []) if user else []
        except RuntimeError:
            roles = []

        if action == "list":
            return handle_list(store, user_id=user_id, roles=roles)

        elif action == "create":
            return handle_create(store, user_id=user_id, data=input)

        elif action == "update":
            return handle_update(store, user_id=user_id, roles=roles, data=input)

        elif action == "delete":
            name = input.get("name", "")
            return handle_delete(store, user_id=user_id, roles=roles, name=name)

        elif action == "status":
            name = input.get("name", "")
            return handle_status(store, name=name)

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
