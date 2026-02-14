"""Tests for MCP Gateway lifecycle hooks (create/delete side effects)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from python.helpers.mcp_gateway_lifecycle import (
    on_server_created,
    on_server_deleted,
)
from python.helpers.mcp_resource_store import McpServerResource


@pytest.fixture
def http_resource():
    return McpServerResource(
        name="github",
        transport_type="streamable_http",
        url="http://localhost:8080/mcp",
        created_by="admin",
    )


@pytest.fixture
def docker_resource():
    return McpServerResource(
        name="docker-server",
        transport_type="streamable_http",
        created_by="admin",
        docker_image="ghcr.io/mcp/server:latest",
        docker_ports={"8080/tcp": 8080},
    )


# ---------- Tests: on_server_created ----------


@pytest.mark.asyncio
async def test_create_mounts_via_compositor(http_resource):
    """on_server_created mounts the server via compositor."""
    compositor = AsyncMock()
    await on_server_created(http_resource, compositor=compositor)
    compositor.mount_server.assert_called_once_with(http_resource)


@pytest.mark.asyncio
async def test_create_starts_docker_container(docker_resource):
    """on_server_created starts Docker container for Docker-backed servers."""
    compositor = AsyncMock()
    container_mgr = MagicMock()
    container_mgr.start_server.return_value = "container-123"

    await on_server_created(
        docker_resource, compositor=compositor, container_manager=container_mgr
    )

    container_mgr.start_server.assert_called_once_with(docker_resource)
    compositor.mount_server.assert_called_once_with(docker_resource)


@pytest.mark.asyncio
async def test_create_skips_docker_if_no_image(http_resource):
    """on_server_created skips Docker start for non-Docker servers."""
    compositor = AsyncMock()
    container_mgr = MagicMock()

    await on_server_created(
        http_resource, compositor=compositor, container_manager=container_mgr
    )

    container_mgr.start_server.assert_not_called()


@pytest.mark.asyncio
async def test_create_handles_mount_error(http_resource):
    """on_server_created handles compositor mount errors gracefully."""
    compositor = AsyncMock()
    compositor.mount_server.side_effect = RuntimeError("mount failed")

    # Should not raise
    await on_server_created(http_resource, compositor=compositor)


# ---------- Tests: on_server_deleted ----------


@pytest.mark.asyncio
async def test_delete_unmounts_via_compositor():
    """on_server_deleted unmounts the server."""
    compositor = AsyncMock()
    pool = AsyncMock()

    await on_server_deleted("github", compositor=compositor, pool=pool)

    compositor.unmount_server.assert_called_once_with("github")


@pytest.mark.asyncio
async def test_delete_evicts_pool_connection():
    """on_server_deleted evicts the pool connection."""
    compositor = AsyncMock()
    pool = AsyncMock()

    await on_server_deleted("github", compositor=compositor, pool=pool)

    pool.evict.assert_called_once_with("github")


@pytest.mark.asyncio
async def test_delete_stops_docker_container():
    """on_server_deleted stops Docker container if manager provided."""
    compositor = AsyncMock()
    pool = AsyncMock()
    container_mgr = MagicMock()

    await on_server_deleted(
        "github",
        compositor=compositor,
        pool=pool,
        container_manager=container_mgr,
    )

    container_mgr.stop_server.assert_called_once_with("github")


@pytest.mark.asyncio
async def test_delete_handles_errors_gracefully():
    """on_server_deleted handles errors without raising."""
    compositor = AsyncMock()
    compositor.unmount_server.side_effect = RuntimeError("unmount failed")
    pool = AsyncMock()

    # Should not raise
    await on_server_deleted("github", compositor=compositor, pool=pool)
