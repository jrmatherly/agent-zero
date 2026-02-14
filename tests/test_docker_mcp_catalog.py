"""Tests for Docker MCP Catalog client."""

from python.helpers.docker_mcp_catalog import (
    parse_catalog_entries,
    catalog_entry_to_resource,
)
from python.helpers.mcp_resource_store import McpServerResource


# ---------- Sample data ----------

SAMPLE_CATALOG = [
    {
        "name": "docker/github-mcp",
        "description": "GitHub MCP server for repository management",
        "image": "ghcr.io/docker/github-mcp:latest",
        "transport": "stdio",
        "args": ["--token", "${GITHUB_TOKEN}"],
    },
    {
        "name": "docker/filesystem-mcp",
        "description": "Filesystem access MCP server",
        "image": "ghcr.io/docker/filesystem-mcp:latest",
        "transport": "streamable_http",
        "port": 8080,
    },
    {
        "name": "docker/slack-mcp",
        "description": "Slack integration MCP server",
        "image": "ghcr.io/docker/slack-mcp:1.2.0",
        "transport": "sse",
        "port": 9090,
        "env": {"SLACK_TOKEN": "${SLACK_TOKEN}"},
    },
]

SAMPLE_YAML = """\
servers:
  - name: docker/github-mcp
    description: GitHub MCP server
    image: ghcr.io/docker/github-mcp:latest
    transport: stdio
  - name: docker/filesystem-mcp
    description: Filesystem access
    image: ghcr.io/docker/filesystem-mcp:latest
    transport: streamable_http
    port: 8080
"""


# ---------- Tests: parse_catalog_entries ----------


def test_parse_returns_list():
    """parse_catalog_entries returns a list of dicts."""
    results = parse_catalog_entries(SAMPLE_CATALOG)
    assert isinstance(results, list)
    assert len(results) == 3


def test_parse_preserves_fields():
    """parse_catalog_entries preserves name, description, image, transport."""
    results = parse_catalog_entries(SAMPLE_CATALOG)
    github = results[0]
    assert github["name"] == "docker/github-mcp"
    assert github["description"] == "GitHub MCP server for repository management"
    assert github["image"] == "ghcr.io/docker/github-mcp:latest"
    assert github["transport"] == "stdio"


def test_parse_empty_list():
    """parse_catalog_entries returns empty list for empty input."""
    assert parse_catalog_entries([]) == []


def test_parse_skips_invalid_entries():
    """parse_catalog_entries skips entries missing required 'name' field."""
    entries = [
        {"description": "No name"},
        {"name": "valid", "image": "img:latest"},
    ]
    results = parse_catalog_entries(entries)
    assert len(results) == 1
    assert results[0]["name"] == "valid"


def test_parse_includes_optional_fields():
    """parse_catalog_entries includes port and env when present."""
    results = parse_catalog_entries(SAMPLE_CATALOG)
    slack = results[2]
    assert slack["port"] == 9090
    assert slack["env"] == {"SLACK_TOKEN": "${SLACK_TOKEN}"}


# ---------- Tests: catalog_entry_to_resource ----------


def test_entry_to_resource_stdio():
    """catalog_entry_to_resource creates stdio resource with Docker image."""
    entry = SAMPLE_CATALOG[0]
    resource = catalog_entry_to_resource(entry, user_id="admin")
    assert isinstance(resource, McpServerResource)
    assert resource.name == "docker/github-mcp"
    assert resource.docker_image == "ghcr.io/docker/github-mcp:latest"
    assert resource.transport_type == "stdio"
    assert resource.created_by == "admin"
    assert resource.is_enabled is True


def test_entry_to_resource_http():
    """catalog_entry_to_resource creates HTTP resource with Docker image and port."""
    entry = SAMPLE_CATALOG[1]
    resource = catalog_entry_to_resource(entry, user_id="admin")
    assert resource.transport_type == "streamable_http"
    assert resource.docker_image == "ghcr.io/docker/filesystem-mcp:latest"
    assert resource.docker_ports == {"8080/tcp": 8080}


def test_entry_to_resource_sse():
    """catalog_entry_to_resource creates SSE resource with Docker image."""
    entry = SAMPLE_CATALOG[2]
    resource = catalog_entry_to_resource(entry, user_id="admin")
    assert resource.transport_type == "sse"
    assert resource.docker_image == "ghcr.io/docker/slack-mcp:1.2.0"
    assert resource.docker_ports == {"9090/tcp": 9090}


def test_entry_to_resource_includes_env():
    """catalog_entry_to_resource includes env vars from catalog entry."""
    entry = SAMPLE_CATALOG[2]
    resource = catalog_entry_to_resource(entry, user_id="admin")
    assert resource.env == {"SLACK_TOKEN": "${SLACK_TOKEN}"}


def test_entry_to_resource_default_transport():
    """catalog_entry_to_resource defaults to streamable_http when transport not specified."""
    entry = {"name": "test", "image": "test:latest"}
    resource = catalog_entry_to_resource(entry, user_id="admin")
    assert resource.transport_type == "streamable_http"


# ---------- Tests: YAML parsing ----------


def test_parse_yaml_content():
    """parse_catalog_entries can work with pre-parsed YAML data."""
    import yaml

    data = yaml.safe_load(SAMPLE_YAML)
    results = parse_catalog_entries(data.get("servers", []))
    assert len(results) == 2
    assert results[0]["name"] == "docker/github-mcp"
    assert results[1]["name"] == "docker/filesystem-mcp"
