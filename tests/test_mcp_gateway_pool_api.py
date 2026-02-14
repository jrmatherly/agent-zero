"""Tests for MCP Gateway Connection Pool API handler.

Tests the McpGatewayPool API handler that exposes pool diagnostics:
status, health_check, and evict operations.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from python.helpers.mcp_connection_pool import McpConnectionPool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pool():
    """Fresh connection pool for each test."""
    return McpConnectionPool(max_connections=10)


@pytest.fixture
async def populated_pool(pool):
    """Pool with two connections."""
    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()

    await pool.acquire("server-a", factory=AsyncMock(return_value=mock_conn1))
    await pool.release("server-a")
    await pool.acquire("server-b", factory=AsyncMock(return_value=mock_conn2))
    await pool.release("server-b")
    return pool


# ---------------------------------------------------------------------------
# Handler structure
# ---------------------------------------------------------------------------


class TestHandlerStructure:
    def test_handler_is_api_handler_subclass(self):
        from python.api.mcp_gateway_pool import McpGatewayPool
        from python.helpers.api import ApiHandler

        assert issubclass(McpGatewayPool, ApiHandler)


# ---------------------------------------------------------------------------
# Status action
# ---------------------------------------------------------------------------


class TestStatusAction:
    def test_status_empty_pool(self, pool):
        from python.api.mcp_gateway_pool import handle_status

        result = handle_status(pool)
        assert result["ok"] is True
        assert result["data"]["active_count"] == 0
        assert result["data"]["connections"] == []

    async def test_status_populated_pool(self, populated_pool):
        from python.api.mcp_gateway_pool import handle_status

        result = handle_status(populated_pool)
        assert result["ok"] is True
        assert result["data"]["active_count"] == 2
        assert len(result["data"]["connections"]) == 2

        names = {c["server_name"] for c in result["data"]["connections"]}
        assert names == {"server-a", "server-b"}

    async def test_status_shows_in_use_flag(self, pool):
        from python.api.mcp_gateway_pool import handle_status

        mock_conn = MagicMock()
        await pool.acquire("active-server", factory=AsyncMock(return_value=mock_conn))
        # Don't release — still in use

        result = handle_status(pool)
        conn_info = result["data"]["connections"][0]
        assert conn_info["in_use"] is True


# ---------------------------------------------------------------------------
# Health check action
# ---------------------------------------------------------------------------


class TestHealthCheckAction:
    async def test_health_check_evicts_unhealthy(self, pool):
        from python.api.mcp_gateway_pool import handle_health_check

        # Create a connection that reports unhealthy
        unhealthy_conn = MagicMock()
        unhealthy_conn.is_healthy = AsyncMock(return_value=False)
        await pool.acquire("bad-server", factory=AsyncMock(return_value=unhealthy_conn))
        await pool.release("bad-server")

        result = await handle_health_check(pool)
        assert result["ok"] is True
        assert pool.active_count == 0

    async def test_health_check_keeps_healthy(self, pool):
        from python.api.mcp_gateway_pool import handle_health_check

        healthy_conn = MagicMock()
        healthy_conn.is_healthy = AsyncMock(return_value=True)
        await pool.acquire("good-server", factory=AsyncMock(return_value=healthy_conn))
        await pool.release("good-server")

        result = await handle_health_check(pool)
        assert result["ok"] is True
        assert pool.active_count == 1


# ---------------------------------------------------------------------------
# Evict action
# ---------------------------------------------------------------------------


class TestEvictAction:
    async def test_evict_existing_connection(self, populated_pool):
        from python.api.mcp_gateway_pool import handle_evict

        result = await handle_evict(populated_pool, name="server-a")
        assert result["ok"] is True
        assert populated_pool.active_count == 1

    async def test_evict_nonexistent_returns_ok(self, pool):
        from python.api.mcp_gateway_pool import handle_evict

        # Evicting a non-existent connection is a no-op (idempotent)
        result = await handle_evict(pool, name="nonexistent")
        assert result["ok"] is True
