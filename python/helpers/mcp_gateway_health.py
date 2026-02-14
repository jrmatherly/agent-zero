"""Gateway health checker for connection pool and Docker containers.

Provides periodic health checking for the MCP gateway, combining
connection pool health checks with Docker container status monitoring.
"""

from __future__ import annotations

import logging
from typing import Any

from python.helpers.mcp_connection_pool import McpConnectionPool
from python.helpers.mcp_container_manager import McpContainerManager
from python.helpers.mcp_resource_store import InMemoryMcpResourceStore

logger = logging.getLogger(__name__)


class McpGatewayHealthChecker:
    """Orchestrates health checks across pool and Docker containers."""

    def __init__(
        self,
        pool: McpConnectionPool,
        store: InMemoryMcpResourceStore,
    ) -> None:
        self._pool = pool
        self._store = store

    async def run_health_check(self) -> dict[str, Any]:
        """Run a full health check on the connection pool."""
        try:
            await self._pool.health_check()
            return {"ok": True, "pool_active": self._pool.active_count}
        except Exception as exc:
            logger.warning("Gateway health check failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def check_docker_servers(self) -> list[dict[str, Any]]:
        """Check Docker container status for Docker-backed servers."""
        results: list[dict[str, Any]] = []
        resources = self._store.list_all()
        docker_resources = [r for r in resources if r.docker_image]

        if not docker_resources:
            return results

        try:
            manager = McpContainerManager()
        except Exception as exc:
            logger.warning("Cannot connect to Docker: %s", exc)
            return [
                {"name": r.name, "running": False, "error": "Docker unavailable"}
                for r in docker_resources
            ]

        for resource in docker_resources:
            status = manager.get_status(resource.name)
            results.append(
                {
                    "name": resource.name,
                    "running": status.get("running", False),
                    "container_id": status.get("container_id"),
                    "status": status.get("status", "unknown"),
                }
            )

        return results

    async def get_status(self) -> dict[str, Any]:
        """Get combined gateway health status."""
        return {
            "pool_connections": self._pool.active_count,
            "registered_servers": len(self._store.list_all()),
        }
