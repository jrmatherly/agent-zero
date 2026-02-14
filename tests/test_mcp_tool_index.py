"""Tests for MCP unified tool index."""

from python.helpers.mcp_tool_index import McpToolIndex


# ---------- Tests: list_all_tools ----------


def test_list_empty():
    """list_all_tools returns empty list when no tools registered."""
    index = McpToolIndex()
    assert index.list_all_tools() == []


def test_register_and_list():
    """register_tools adds tools that appear in list_all_tools."""
    index = McpToolIndex()
    index.register_tools(
        "github",
        [
            {"name": "create_issue", "description": "Create a GitHub issue"},
            {"name": "list_repos", "description": "List repositories"},
        ],
    )
    tools = index.list_all_tools()
    assert len(tools) == 2
    assert tools[0]["server"] == "github"
    assert tools[0]["name"] == "create_issue"


def test_register_multiple_servers():
    """register_tools from multiple servers are all listed."""
    index = McpToolIndex()
    index.register_tools("github", [{"name": "create_issue", "description": ""}])
    index.register_tools("filesystem", [{"name": "read_file", "description": ""}])
    tools = index.list_all_tools()
    assert len(tools) == 2
    servers = {t["server"] for t in tools}
    assert servers == {"github", "filesystem"}


def test_unregister_server():
    """unregister_server removes all tools for that server."""
    index = McpToolIndex()
    index.register_tools("github", [{"name": "create_issue", "description": ""}])
    index.register_tools("filesystem", [{"name": "read_file", "description": ""}])
    index.unregister_server("github")
    tools = index.list_all_tools()
    assert len(tools) == 1
    assert tools[0]["server"] == "filesystem"


def test_unregister_nonexistent():
    """unregister_server for unknown server is a no-op."""
    index = McpToolIndex()
    index.unregister_server("nonexistent")
    assert index.list_all_tools() == []


# ---------- Tests: search_tools ----------


def test_search_by_name():
    """search_tools matches tool name."""
    index = McpToolIndex()
    index.register_tools(
        "github",
        [
            {"name": "create_issue", "description": "Create a GitHub issue"},
            {"name": "list_repos", "description": "List repositories"},
        ],
    )
    results = index.search_tools("issue")
    assert len(results) == 1
    assert results[0]["name"] == "create_issue"


def test_search_by_description():
    """search_tools matches tool description."""
    index = McpToolIndex()
    index.register_tools(
        "fs",
        [
            {"name": "read_file", "description": "Read a file from the local disk"},
            {"name": "write_file", "description": "Write data to a file"},
        ],
    )
    results = index.search_tools("local disk")
    assert len(results) == 1
    assert results[0]["name"] == "read_file"


def test_search_case_insensitive():
    """search_tools is case-insensitive."""
    index = McpToolIndex()
    index.register_tools("github", [{"name": "CreateIssue", "description": "Creates"}])
    results = index.search_tools("createissue")
    assert len(results) == 1


def test_search_empty_query():
    """search_tools with empty query returns all tools."""
    index = McpToolIndex()
    index.register_tools("github", [{"name": "a", "description": ""}])
    index.register_tools("fs", [{"name": "b", "description": ""}])
    results = index.search_tools("")
    assert len(results) == 2


def test_search_no_results():
    """search_tools returns empty list when nothing matches."""
    index = McpToolIndex()
    index.register_tools("github", [{"name": "create_issue", "description": "Create"}])
    results = index.search_tools("kubernetes")
    assert results == []


def test_search_by_server_name():
    """search_tools matches server name."""
    index = McpToolIndex()
    index.register_tools("github", [{"name": "create_issue", "description": ""}])
    index.register_tools("filesystem", [{"name": "read_file", "description": ""}])
    results = index.search_tools("github")
    assert len(results) == 1
    assert results[0]["server"] == "github"


# ---------- Tests: tool_count ----------


def test_tool_count():
    """tool_count returns total registered tools."""
    index = McpToolIndex()
    assert index.tool_count == 0
    index.register_tools("a", [{"name": "t1", "description": ""}])
    assert index.tool_count == 1
    index.register_tools(
        "b", [{"name": "t2", "description": ""}, {"name": "t3", "description": ""}]
    )
    assert index.tool_count == 3
