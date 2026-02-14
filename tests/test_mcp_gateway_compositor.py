"""Tests for MCP Gateway Compositor.

Tests the McpGatewayCompositor that mounts/unmounts MCP servers on a
FastMCP instance using create_proxy() and mount().
"""

import pytest

from fastmcp import FastMCP

from python.helpers.mcp_resource_store import McpServerResource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def main_server():
    """Fresh FastMCP server for composition."""
    return FastMCP("test-gateway")


@pytest.fixture
def compositor(main_server):
    """Compositor bound to the test server."""
    from python.helpers.mcp_gateway_compositor import McpGatewayCompositor

    return McpGatewayCompositor(main_server)


@pytest.fixture
def http_resource():
    """HTTP-based MCP server resource."""
    return McpServerResource(
        name="github",
        transport_type="streamable_http",
        url="http://mcp-github:8000/mcp",
        created_by="admin",
    )


@pytest.fixture
def stdio_resource():
    """Stdio-based MCP server resource."""
    return McpServerResource(
        name="filesystem",
        transport_type="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"],
        created_by="admin",
    )


# ---------------------------------------------------------------------------
# Mounting
# ---------------------------------------------------------------------------


class TestMountServer:
    """Test mounting servers onto the FastMCP instance."""

    async def test_mount_http_server_adds_provider(
        self, main_server, compositor, http_resource
    ):
        initial_count = len(main_server.providers)
        await compositor.mount_server(http_resource)

        assert len(main_server.providers) == initial_count + 1
        assert "github" in compositor.mounted_names

    async def test_mount_stdio_server_adds_provider(
        self, main_server, compositor, stdio_resource
    ):
        initial_count = len(main_server.providers)
        await compositor.mount_server(stdio_resource)

        assert len(main_server.providers) == initial_count + 1
        assert "filesystem" in compositor.mounted_names

    async def test_mount_multiple_servers(
        self, main_server, compositor, http_resource, stdio_resource
    ):
        initial_count = len(main_server.providers)
        await compositor.mount_server(http_resource)
        await compositor.mount_server(stdio_resource)

        assert len(main_server.providers) == initial_count + 2
        assert compositor.mounted_names == {"github", "filesystem"}

    async def test_mount_disabled_server_skipped(self, compositor):
        resource = McpServerResource(
            name="disabled",
            transport_type="streamable_http",
            url="http://disabled:8000/mcp",
            created_by="admin",
            is_enabled=False,
        )
        await compositor.mount_server(resource)
        assert "disabled" not in compositor.mounted_names

    async def test_namespace_collision_raises(self, compositor, http_resource):
        await compositor.mount_server(http_resource)

        duplicate = McpServerResource(
            name="github",
            transport_type="streamable_http",
            url="http://other-github:8000/mcp",
            created_by="admin",
        )
        with pytest.raises(ValueError, match="already mounted"):
            await compositor.mount_server(duplicate)


# ---------------------------------------------------------------------------
# Unmounting
# ---------------------------------------------------------------------------


class TestUnmountServer:
    """Test removing mounted servers."""

    async def test_unmount_removes_provider(
        self, main_server, compositor, http_resource
    ):
        initial_count = len(main_server.providers)
        await compositor.mount_server(http_resource)
        assert len(main_server.providers) == initial_count + 1

        await compositor.unmount_server("github")
        assert len(main_server.providers) == initial_count
        assert "github" not in compositor.mounted_names

    async def test_unmount_nonexistent_is_noop(self, compositor):
        # Should not raise
        await compositor.unmount_server("nonexistent")

    async def test_unmount_preserves_other_mounts(
        self, main_server, compositor, http_resource, stdio_resource
    ):
        initial_count = len(main_server.providers)
        await compositor.mount_server(http_resource)
        await compositor.mount_server(stdio_resource)

        await compositor.unmount_server("github")
        assert len(main_server.providers) == initial_count + 1
        assert "filesystem" in compositor.mounted_names
        assert "github" not in compositor.mounted_names

    async def test_remount_after_unmount(self, main_server, compositor, http_resource):
        initial_count = len(main_server.providers)
        await compositor.mount_server(http_resource)
        await compositor.unmount_server("github")

        # Should be able to re-mount without collision
        await compositor.mount_server(http_resource)
        assert len(main_server.providers) == initial_count + 1
        assert "github" in compositor.mounted_names


# ---------------------------------------------------------------------------
# Disable / Enable
# ---------------------------------------------------------------------------


class TestDisableEnable:
    """Test temporary visibility control."""

    async def test_disable_hides_tools(self, main_server, compositor, http_resource):
        await compositor.mount_server(http_resource)
        await compositor.disable_server("github")

        # Server still tracked as mounted
        assert "github" in compositor.mounted_names
        # Provider still in list (just disabled)
        assert compositor.is_disabled("github")

    async def test_enable_restores_tools(self, main_server, compositor, http_resource):
        await compositor.mount_server(http_resource)
        await compositor.disable_server("github")
        await compositor.enable_server("github")

        assert not compositor.is_disabled("github")

    async def test_disable_nonexistent_is_noop(self, compositor):
        # Should not raise
        await compositor.disable_server("nonexistent")

    async def test_enable_nonexistent_is_noop(self, compositor):
        # Should not raise
        await compositor.enable_server("nonexistent")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test that errors in mount don't crash the compositor."""

    async def test_unsupported_transport_type_skipped(self, compositor):
        resource = McpServerResource(
            name="unknown",
            transport_type="unsupported_transport",
            created_by="admin",
        )
        await compositor.mount_server(resource)
        assert "unknown" not in compositor.mounted_names

    async def test_http_resource_without_url_skipped(self, compositor):
        resource = McpServerResource(
            name="no-url",
            transport_type="streamable_http",
            url=None,
            created_by="admin",
        )
        await compositor.mount_server(resource)
        assert "no-url" not in compositor.mounted_names

    async def test_stdio_resource_without_command_skipped(self, compositor):
        resource = McpServerResource(
            name="no-cmd",
            transport_type="stdio",
            command=None,
            created_by="admin",
        )
        await compositor.mount_server(resource)
        assert "no-cmd" not in compositor.mounted_names
