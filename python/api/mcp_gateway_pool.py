"""MCP Gateway connection pool status and health API.

Exposes pool diagnostics: status, health_check, and evict operations.
"""

import json
from typing import Any

from python.helpers.api import ApiHandler, Request, Response
from python.helpers.mcp_connection_pool import McpConnectionPool

# Module-level pool singleton
_pool = McpConnectionPool(max_connections=20)


def get_pool() -> McpConnectionPool:
    """Return the module-level connection pool singleton."""
    return _pool


def handle_status(pool: McpConnectionPool) -> dict[str, Any]:
    """Return pool status with active count and connection details."""
    connections = []
    for name, pooled in pool._connections.items():
        connections.append(
            {
                "server_name": pooled.server_name,
                "in_use": pooled.in_use,
                "last_used_at": pooled.last_used_at,
                "created_at": pooled.created_at,
            }
        )

    return {
        "ok": True,
        "data": {
            "active_count": pool.active_count,
            "max_connections": pool.max_connections,
            "connections": connections,
        },
    }


async def handle_health_check(pool: McpConnectionPool) -> dict[str, Any]:
    """Trigger health check and return results."""
    before = pool.active_count
    await pool.health_check()
    after = pool.active_count
    evicted = before - after

    return {
        "ok": True,
        "data": {
            "checked": before,
            "evicted": evicted,
            "remaining": after,
        },
    }


async def handle_evict(pool: McpConnectionPool, name: str) -> dict[str, Any]:
    """Evict a specific connection by server name."""
    await pool.evict(name)
    return {"ok": True}


class McpGatewayPool(ApiHandler):
    """Connection pool status and health API handler."""

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        # Dynamic: status uses read, health_check/evict use write
        return None

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action", "status")
        pool = get_pool()

        if action == "status":
            return handle_status(pool)

        elif action == "health_check":
            return await handle_health_check(pool)

        elif action == "evict":
            name = input.get("name", "")
            if not name:
                return Response(
                    json.dumps({"error": "Missing required field: name"}),
                    status=400,
                    mimetype="application/json",
                )
            return await handle_evict(pool, name=name)

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
