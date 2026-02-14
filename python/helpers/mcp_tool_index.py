"""Unified tool index across mounted MCP servers.

Provides a searchable index of all tools exposed by gateway-mounted
MCP servers, enabling keyword search and tool listing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class McpToolIndex:
    """Keyword-searchable index of tools from mounted MCP servers."""

    def __init__(self) -> None:
        # server_name -> list of tool dicts
        self._tools: dict[str, list[dict[str, Any]]] = {}

    @property
    def tool_count(self) -> int:
        """Return total number of registered tools."""
        return sum(len(tools) for tools in self._tools.values())

    def register_tools(self, server_name: str, tools: list[dict[str, Any]]) -> None:
        """Register tools from a mounted server."""
        self._tools[server_name] = [
            {
                "server": server_name,
                "name": t.get("name", ""),
                "description": t.get("description", ""),
            }
            for t in tools
        ]
        logger.debug("Registered %d tools from server '%s'", len(tools), server_name)

    def unregister_server(self, server_name: str) -> None:
        """Remove all tools for a server."""
        self._tools.pop(server_name, None)

    def list_all_tools(self) -> list[dict[str, Any]]:
        """Return all registered tools across all servers."""
        result = []
        for tools in self._tools.values():
            result.extend(tools)
        return result

    def search_tools(self, query: str) -> list[dict[str, Any]]:
        """Keyword search across tool names, descriptions, and server names."""
        if not query:
            return self.list_all_tools()

        query_lower = query.lower()
        results = []
        for tools in self._tools.values():
            for tool in tools:
                searchable = (
                    f"{tool['name']} {tool['description']} {tool['server']}"
                ).lower()
                if query_lower in searchable:
                    results.append(tool)
        return results
