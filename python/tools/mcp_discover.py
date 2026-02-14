"""Agent tool for discovering and installing MCP servers.

Enables the agent to search the MCP Registry and Docker MCP Catalog
during its monologue loop, and install servers into the gateway.
"""

from python.helpers.mcp_registry_client import McpRegistryClient
from python.helpers.mcp_tool_index import McpToolIndex
from python.helpers.tool import Response, Tool

# Module-level singletons
_registry_client = McpRegistryClient()
_tool_index = McpToolIndex()


def get_tool_index() -> McpToolIndex:
    """Return the module-level tool index singleton."""
    return _tool_index


class McpDiscover(Tool):
    async def execute(self, **kwargs):
        action = self.args.get("action", "search")

        if action == "search":
            return await self._search()
        elif action == "list":
            return self._list_tools()
        elif action == "search_tools":
            return self._search_tools()

        return Response(
            message=f"Unknown action: {action}. Use 'search', 'list', or 'search_tools'.",
            break_loop=False,
        )

    async def _search(self) -> Response:
        """Search the MCP Registry for servers."""
        query = self.args.get("query", "")
        if not query:
            return Response(
                message="Please provide a 'query' argument to search for MCP servers.",
                break_loop=False,
            )

        results = await _registry_client.search(query, limit=10)
        if not results:
            return Response(
                message=f"No MCP servers found matching '{query}'.",
                break_loop=False,
            )

        lines = [f"Found {len(results)} MCP server(s) matching '{query}':\n"]
        for r in results:
            packages = ", ".join(
                f"{p['registry_name']}:{p['name']}" for p in r.get("packages", [])
            )
            lines.append(f"- **{r['name']}**: {r.get('description', 'No description')}")
            if packages:
                lines.append(f"  Packages: {packages}")

        return Response(message="\n".join(lines), break_loop=False)

    def _list_tools(self) -> Response:
        """List all tools available across mounted MCP servers."""
        tools = _tool_index.list_all_tools()
        if not tools:
            return Response(
                message="No MCP server tools currently registered in the tool index.",
                break_loop=False,
            )

        lines = [f"Available MCP tools ({len(tools)} total):\n"]
        by_server: dict[str, list[str]] = {}
        for t in tools:
            by_server.setdefault(t["server"], []).append(
                f"  - {t['name']}: {t['description']}"
            )

        for server, tool_lines in sorted(by_server.items()):
            lines.append(f"**{server}**:")
            lines.extend(tool_lines)

        return Response(message="\n".join(lines), break_loop=False)

    def _search_tools(self) -> Response:
        """Search across all registered tools."""
        query = self.args.get("query", "")
        if not query:
            return Response(
                message="Please provide a 'query' argument to search tools.",
                break_loop=False,
            )

        results = _tool_index.search_tools(query)
        if not results:
            return Response(
                message=f"No tools found matching '{query}'.",
                break_loop=False,
            )

        lines = [f"Found {len(results)} tool(s) matching '{query}':\n"]
        for t in results:
            lines.append(f"- **{t['server']}/{t['name']}**: {t['description']}")

        return Response(message="\n".join(lines), break_loop=False)
