"""Tests for MCP connection pool with persistent sessions."""

from unittest.mock import AsyncMock, MagicMock


class TestMcpConnectionPool:
    """Test the MCP connection pool manages persistent connections."""

    def test_pool_starts_empty(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        assert pool.active_count == 0

    def test_pool_has_max_size(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool(max_connections=5)
        assert pool.max_connections == 5

    async def test_acquire_creates_connection(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        mock_factory = AsyncMock(return_value=MagicMock())
        conn = await pool.acquire("test-server", factory=mock_factory)
        assert conn is not None
        assert pool.active_count == 1
        mock_factory.assert_awaited_once()

    async def test_acquire_reuses_existing(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        mock_factory = AsyncMock(return_value=MagicMock())
        conn1 = await pool.acquire("test-server", factory=mock_factory)
        conn2 = await pool.acquire("test-server", factory=mock_factory)
        assert conn1 is conn2
        assert pool.active_count == 1
        mock_factory.assert_awaited_once()  # only created once

    async def test_release_marks_idle(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        mock_factory = AsyncMock(return_value=MagicMock())
        await pool.acquire("test-server", factory=mock_factory)
        await pool.release("test-server")
        assert pool.active_count == 1  # still in pool, just idle

    async def test_evict_removes_connection(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        mock_conn = AsyncMock()
        mock_factory = AsyncMock(return_value=mock_conn)
        pool = McpConnectionPool()
        await pool.acquire("test-server", factory=mock_factory)
        await pool.evict("test-server")
        assert pool.active_count == 0

    async def test_health_check_evicts_unhealthy(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        mock_conn = MagicMock()
        mock_conn.is_healthy = AsyncMock(return_value=False)
        mock_factory = AsyncMock(return_value=mock_conn)
        pool = McpConnectionPool()
        await pool.acquire("test-server", factory=mock_factory)
        await pool.health_check()
        assert pool.active_count == 0
