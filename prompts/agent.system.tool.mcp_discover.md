### mcp_discover:
Search MCP Registry for servers, list available tools, or search tools across mounted servers.
Actions: "search" (find servers by keyword), "list" (show all mounted tools), "search_tools" (find tools by keyword)
**Example usage**:

~~~json
{
    "thoughts": [
        "I need to find an MCP server for GitHub integration",
    ],
    "headline": "Searching MCP Registry for GitHub servers",
    "tool_name": "mcp_discover",
    "tool_args": {
        "action": "search",
        "query": "github"
    }
}
~~~

~~~json
{
    "thoughts": [
        "Let me check what tools are available from mounted MCP servers",
    ],
    "headline": "Listing available MCP tools",
    "tool_name": "mcp_discover",
    "tool_args": {
        "action": "list"
    }
}
~~~
