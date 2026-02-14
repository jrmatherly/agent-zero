"""Client for the Official MCP Registry API.

Queries https://registry.modelcontextprotocol.io/v0/servers for
server discovery, with cursor-based pagination and error resilience.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"


class McpRegistryClient:
    """Async client for the MCP Registry discovery API."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def search(
        self,
        query: str = "",
        limit: int = 20,
        cursor: str | None = None,
    ) -> list[dict]:
        """Search the MCP Registry for servers.

        Raises on network/parsing errors so callers can surface them.
        """
        params: dict = {"limit": limit}
        if query:
            params["search"] = query
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(REGISTRY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        return [self._parse_server(entry) for entry in data.get("servers", [])]

    async def search_all(
        self,
        query: str = "",
        max_pages: int = 10,
    ) -> list[dict]:
        """Paginate through all matching servers up to max_pages."""
        results: list[dict] = []
        cursor: str | None = None

        for _ in range(max_pages):
            params: dict = {"limit": 100}
            if query:
                params["search"] = query
            if cursor:
                params["cursor"] = cursor

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(REGISTRY_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
            except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
                logger.warning("MCP Registry pagination failed: %s", exc)
                break

            servers = data.get("servers", [])
            results.extend(self._parse_server(entry) for entry in servers)

            next_cursor = data.get("metadata", {}).get("nextCursor")
            if not next_cursor:
                break
            cursor = next_cursor

        return results

    @staticmethod
    def _parse_server(entry: dict) -> dict:
        """Extract a flat server dict from the registry response format.

        The registry API returns servers with either 'packages' (local installs)
        or 'remotes' (hosted endpoints), or both.
        """
        server = entry.get("server", {})
        return {
            "name": server.get("name", ""),
            "description": server.get("description", ""),
            "packages": server.get("packages", []),
            "remotes": server.get("remotes", []),
            "version": server.get("version", ""),
            "repository": server.get("repository", {}),
        }
