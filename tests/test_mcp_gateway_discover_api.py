"""Tests for MCP Gateway discovery API endpoint."""

from unittest.mock import AsyncMock, patch

import pytest

from python.api.mcp_gateway_discover import handle_search, handle_install
from python.helpers.mcp_resource_store import InMemoryMcpResourceStore


SAMPLE_RESULT = {
    "name": "github",
    "description": "GitHub MCP server",
    "packages": [
        {
            "registry_name": "npm",
            "name": "@modelcontextprotocol/server-github",
            "version": "1.0.0",
        }
    ],
}


# ---------- Tests: search ----------


@pytest.mark.asyncio
async def test_search_proxies_to_registry_client():
    """handle_search passes query to registry client and returns results."""
    with patch("python.api.mcp_gateway_discover._get_registry_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.search.return_value = [SAMPLE_RESULT]
        mock_get.return_value = mock_client

        result = await handle_search(query="github", limit=10)

    assert result["ok"] is True
    assert len(result["data"]) == 1
    assert result["data"][0]["name"] == "github"
    mock_client.search.assert_called_once_with("github", limit=10)


@pytest.mark.asyncio
async def test_search_empty_query():
    """handle_search with empty query returns all results."""
    with patch("python.api.mcp_gateway_discover._get_registry_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.search.return_value = []
        mock_get.return_value = mock_client

        result = await handle_search(query="", limit=20)

    assert result["ok"] is True
    assert result["data"] == []


@pytest.mark.asyncio
async def test_search_returns_error_on_exception():
    """handle_search returns error dict on unexpected exceptions."""
    with patch("python.api.mcp_gateway_discover._get_registry_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.search.side_effect = RuntimeError("boom")
        mock_get.return_value = mock_client

        result = await handle_search(query="test")

    assert result["ok"] is False
    assert "error" in result


# ---------- Tests: install ----------


@pytest.mark.asyncio
async def test_install_creates_resource():
    """handle_install creates a McpServerResource from registry data."""
    store = InMemoryMcpResourceStore()
    result = await handle_install(
        store=store,
        user_id="user1",
        server_data={
            "name": "github",
            "description": "GitHub MCP server",
            "packages": [
                {
                    "registry_name": "npm",
                    "name": "@modelcontextprotocol/server-github",
                    "version": "1.0.0",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert result["data"]["name"] == "github"
    assert store.get("github") is not None
    assert store.get("github").transport_type == "stdio"
    assert store.get("github").command == "npx"


@pytest.mark.asyncio
async def test_install_missing_name():
    """handle_install returns error when name is missing."""
    store = InMemoryMcpResourceStore()
    result = await handle_install(
        store=store,
        user_id="user1",
        server_data={"description": "No name"},
    )

    assert result["ok"] is False
    assert "name" in result["error"].lower()


@pytest.mark.asyncio
async def test_install_npm_package_sets_stdio():
    """handle_install infers stdio transport for npm packages."""
    store = InMemoryMcpResourceStore()
    result = await handle_install(
        store=store,
        user_id="user1",
        server_data={
            "name": "test-server",
            "packages": [
                {"registry_name": "npm", "name": "@test/mcp-server", "version": "2.0.0"}
            ],
        },
    )

    assert result["ok"] is True
    resource = store.get("test-server")
    assert resource.transport_type == "stdio"
    assert resource.command == "npx"
    assert "-y" in resource.args
    assert "@test/mcp-server@2.0.0" in resource.args


@pytest.mark.asyncio
async def test_install_pip_package_sets_stdio():
    """handle_install infers stdio transport for pip/PyPI packages."""
    store = InMemoryMcpResourceStore()
    result = await handle_install(
        store=store,
        user_id="user1",
        server_data={
            "name": "py-server",
            "packages": [
                {"registry_name": "pip", "name": "mcp-server-py", "version": "1.0.0"}
            ],
        },
    )

    assert result["ok"] is True
    resource = store.get("py-server")
    assert resource.transport_type == "stdio"
    assert resource.command == "uvx"
    assert "mcp-server-py" in resource.args


@pytest.mark.asyncio
async def test_install_docker_package_sets_http():
    """handle_install infers HTTP transport for Docker packages."""
    store = InMemoryMcpResourceStore()
    result = await handle_install(
        store=store,
        user_id="user1",
        server_data={
            "name": "docker-server",
            "packages": [
                {"registry_name": "docker", "name": "mcp/server", "version": "latest"}
            ],
        },
    )

    assert result["ok"] is True
    resource = store.get("docker-server")
    assert resource.docker_image == "mcp/server:latest"


@pytest.mark.asyncio
async def test_install_no_packages_defaults_to_http():
    """handle_install defaults to streamable_http when no packages specified."""
    store = InMemoryMcpResourceStore()
    result = await handle_install(
        store=store,
        user_id="user1",
        server_data={"name": "bare-server", "packages": []},
    )

    assert result["ok"] is True
    resource = store.get("bare-server")
    assert resource.transport_type == "streamable_http"
