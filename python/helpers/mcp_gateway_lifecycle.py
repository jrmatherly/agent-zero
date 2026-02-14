"""Gateway lifecycle hooks for server create/delete events.

Orchestrates side effects when gateway servers are registered or removed:
- Mount/unmount via compositor
- Docker container start/stop
- Connection pool eviction
"""

from __future__ import annotations

import logging
from typing import Any

from python.helpers.mcp_connection_pool import McpConnectionPool
from python.helpers.mcp_gateway_compositor import McpGatewayCompositor
from python.helpers.mcp_resource_store import McpServerResource

logger = logging.getLogger(__name__)


async def on_server_created(
    resource: McpServerResource,
    *,
    compositor: McpGatewayCompositor,
    container_manager: Any | None = None,
) -> None:
    """Handle side effects after a gateway server is created/registered.

    1. Start Docker container if Docker-backed
    2. Mount the server via compositor
    """
    # Start Docker container if applicable
    if resource.docker_image and container_manager is not None:
        try:
            container_id = container_manager.start_server(resource)
            logger.info(
                "Started Docker container for '%s': %s",
                resource.name,
                container_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to start Docker container for '%s': %s",
                resource.name,
                exc,
            )

    # Mount via compositor
    try:
        await compositor.mount_server(resource)
    except Exception as exc:
        logger.warning("Failed to mount gateway server '%s': %s", resource.name, exc)


async def on_server_deleted(
    name: str,
    *,
    compositor: McpGatewayCompositor,
    pool: McpConnectionPool,
    container_manager: Any | None = None,
) -> None:
    """Handle side effects after a gateway server is deleted.

    1. Unmount from compositor
    2. Evict from connection pool
    3. Stop Docker container if applicable
    """
    # Unmount
    try:
        await compositor.unmount_server(name)
    except Exception as exc:
        logger.warning("Failed to unmount server '%s': %s", name, exc)

    # Evict pool connection
    try:
        await pool.evict(name)
    except Exception as exc:
        logger.warning("Failed to evict pool connection '%s': %s", name, exc)

    # Stop Docker container if applicable
    if container_manager is not None:
        try:
            container_manager.stop_server(name)
            logger.info("Stopped Docker container for '%s'", name)
        except Exception as exc:
            logger.warning("Failed to stop Docker container for '%s': %s", name, exc)
