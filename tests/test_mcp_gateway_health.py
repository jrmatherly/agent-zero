"""Tests for MCP Gateway health check and lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python.helpers.mcp_gateway_health import McpGatewayHealthChecker


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    pool.health_check = AsyncMock()
    pool.active_count = 0
    pool._connections = {}
    return pool


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.list_all.return_value = []
    return store


@pytest.fixture
def checker(mock_pool, mock_store):
    return McpGatewayHealthChecker(pool=mock_pool, store=mock_store)


# ---------- Tests: run_health_check ----------


@pytest.mark.asyncio
async def test_health_check_calls_pool(checker, mock_pool):
    """run_health_check invokes pool.health_check()."""
    await checker.run_health_check()
    mock_pool.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_returns_result(checker):
    """run_health_check returns a result dict."""
    result = await checker.run_health_check()
    assert "ok" in result
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_health_check_handles_pool_error(checker, mock_pool):
    """run_health_check handles pool errors gracefully."""
    mock_pool.health_check.side_effect = RuntimeError("pool broken")
    result = await checker.run_health_check()
    assert result["ok"] is False
    assert "error" in result


# ---------- Tests: check_docker_servers ----------


@pytest.mark.asyncio
async def test_check_docker_skips_non_docker(checker, mock_store):
    """check_docker_servers skips servers without docker_image."""
    from python.helpers.mcp_resource_store import McpServerResource

    mock_store.list_all.return_value = [
        McpServerResource(name="local", transport_type="stdio", created_by="admin")
    ]
    result = await checker.check_docker_servers()
    assert result == []


@pytest.mark.asyncio
async def test_check_docker_reports_status(checker, mock_store):
    """check_docker_servers reports status for Docker-backed servers."""
    from python.helpers.mcp_resource_store import McpServerResource

    mock_store.list_all.return_value = [
        McpServerResource(
            name="github",
            transport_type="stdio",
            created_by="admin",
            docker_image="ghcr.io/mcp/github:latest",
        )
    ]
    with patch("python.helpers.mcp_gateway_health.McpContainerManager") as mock_mgr_cls:
        mock_mgr = MagicMock()
        mock_mgr.get_status.return_value = {
            "running": True,
            "container_id": "abc123",
            "status": "running",
        }
        mock_mgr_cls.return_value = mock_mgr

        result = await checker.check_docker_servers()

    assert len(result) == 1
    assert result[0]["name"] == "github"
    assert result[0]["running"] is True


# ---------- Tests: get_status ----------


@pytest.mark.asyncio
async def test_get_status_includes_pool_and_store_info(checker, mock_pool, mock_store):
    """get_status returns combined pool and store information."""
    mock_pool.active_count = 3
    mock_store.list_all.return_value = [MagicMock(), MagicMock()]

    result = await checker.get_status()
    assert result["pool_connections"] == 3
    assert result["registered_servers"] == 2
