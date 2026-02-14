"""Tests for MCP Registry discovery client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from python.helpers.mcp_registry_client import REGISTRY_URL, McpRegistryClient

# ---------- Fixtures ----------


@pytest.fixture
def client():
    return McpRegistryClient()


def _make_response(json_data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


SAMPLE_SERVER = {
    "server": {
        "name": "github",
        "description": "GitHub MCP server for repository management",
        "packages": [
            {
                "registry_name": "npm",
                "name": "@modelcontextprotocol/server-github",
                "version": "1.0.0",
            }
        ],
    },
    "_meta": {"updated_at": "2025-06-01T00:00:00Z"},
}


# ---------- Tests: search ----------


@pytest.mark.asyncio
async def test_search_returns_servers(client):
    """search() returns parsed server list from registry API."""
    response_data = {
        "servers": [SAMPLE_SERVER],
        "metadata": {"count": 1, "nextCursor": None},
    }
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(response_data)

        results = await client.search("github")

    assert len(results) == 1
    assert results[0]["name"] == "github"
    assert results[0]["description"] == "GitHub MCP server for repository management"
    assert len(results[0]["packages"]) == 1
    assert results[0]["remotes"] == []
    assert results[0]["version"] == ""


@pytest.mark.asyncio
async def test_search_empty_query(client):
    """search() with empty query returns all servers."""
    response_data = {
        "servers": [SAMPLE_SERVER],
        "metadata": {"count": 1, "nextCursor": None},
    }
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(response_data)

        results = await client.search("")

    mock_client.get.assert_called_once()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_with_limit(client):
    """search() passes limit parameter to API."""
    response_data = {"servers": [], "metadata": {"count": 0, "nextCursor": None}}
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(response_data)

        await client.search("test", limit=5)

    call_kwargs = mock_client.get.call_args
    assert call_kwargs[1]["params"]["limit"] == 5


@pytest.mark.asyncio
async def test_search_with_cursor(client):
    """search() passes cursor for pagination."""
    response_data = {"servers": [], "metadata": {"count": 0, "nextCursor": None}}
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(response_data)

        await client.search("test", cursor="abc123")

    call_kwargs = mock_client.get.call_args
    assert call_kwargs[1]["params"]["cursor"] == "abc123"


@pytest.mark.asyncio
async def test_search_empty_results(client):
    """search() returns empty list when no servers match."""
    response_data = {"servers": [], "metadata": {"count": 0, "nextCursor": None}}
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(response_data)

        results = await client.search("nonexistent")

    assert results == []


# ---------- Tests: error handling ----------


@pytest.mark.asyncio
async def test_search_network_error_raises(client):
    """search() raises on network errors so callers can surface them."""
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(httpx.ConnectError):
            await client.search("test")


@pytest.mark.asyncio
async def test_search_timeout_raises(client):
    """search() raises on timeout so callers can surface them."""
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("Timed out")

        with pytest.raises(httpx.TimeoutException):
            await client.search("test")


@pytest.mark.asyncio
async def test_search_http_error_raises(client):
    """search() raises on HTTP error status so callers can surface them."""
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response({}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            await client.search("test")


# ---------- Tests: search_all (pagination) ----------


@pytest.mark.asyncio
async def test_search_all_paginates(client):
    """search_all() follows nextCursor until exhausted."""
    page1 = {
        "servers": [SAMPLE_SERVER],
        "metadata": {"count": 1, "nextCursor": "page2_cursor"},
    }
    server2 = {
        "server": {
            "name": "filesystem",
            "description": "Filesystem MCP server",
            "packages": [],
        },
        "_meta": {},
    }
    page2 = {
        "servers": [server2],
        "metadata": {"count": 1, "nextCursor": None},
    }

    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = [
            _make_response(page1),
            _make_response(page2),
        ]

        results = await client.search_all("test")

    assert len(results) == 2
    assert results[0]["name"] == "github"
    assert results[1]["name"] == "filesystem"
    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_search_all_max_pages_limit(client):
    """search_all() stops after max_pages to prevent infinite loops."""
    page_data = {
        "servers": [SAMPLE_SERVER],
        "metadata": {"count": 1, "nextCursor": "always_more"},
    }

    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(page_data)

        results = await client.search_all("test", max_pages=3)

    assert mock_client.get.call_count == 3
    assert len(results) == 3


# ---------- Tests: response parsing ----------


@pytest.mark.asyncio
async def test_parse_extracts_transport_from_packages(client):
    """Parsed result includes transport info inferred from packages."""
    server_with_npm = {
        "server": {
            "name": "test-server",
            "description": "Test",
            "packages": [
                {
                    "registry_name": "npm",
                    "name": "@test/mcp-server",
                    "version": "1.0.0",
                }
            ],
        },
        "_meta": {},
    }
    response_data = {
        "servers": [server_with_npm],
        "metadata": {"count": 1, "nextCursor": None},
    }
    with patch("python.helpers.mcp_registry_client.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _make_response(response_data)

        results = await client.search("test")

    assert results[0]["packages"][0]["registry_name"] == "npm"


# ---------- Tests: configurable timeout ----------


def test_custom_timeout():
    """Client accepts custom timeout."""
    c = McpRegistryClient(timeout=30.0)
    assert c.timeout == 30.0


def test_default_timeout():
    """Default timeout is 10 seconds."""
    c = McpRegistryClient()
    assert c.timeout == 10.0


# ---------- Tests: URL ----------


def test_registry_url_constant():
    """Registry URL points to official MCP registry."""
    assert "registry.modelcontextprotocol.io" in REGISTRY_URL
    assert "/v0/servers" in REGISTRY_URL
