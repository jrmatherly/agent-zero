"""Docker MCP Catalog client for browsing and installing catalog servers.

Supports parsing Docker MCP Catalog entries (from YAML export or API)
and converting them to McpServerResource objects for the gateway store.

Usage:
    docker mcp catalog show docker-mcp > catalog.yaml
    # Then import via API or load programmatically
"""

from __future__ import annotations

import logging
from typing import Any

from python.helpers.mcp_resource_store import McpServerResource

logger = logging.getLogger(__name__)


def parse_catalog_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse and validate a list of Docker MCP Catalog entries.

    Accepts raw catalog data (from YAML parse or API response).
    Skips entries missing the required 'name' field.
    """
    results = []
    for entry in entries:
        name = entry.get("name")
        if not name:
            logger.debug("Skipping catalog entry without name")
            continue

        parsed: dict[str, Any] = {
            "name": name,
            "description": entry.get("description", ""),
            "image": entry.get("image", ""),
            "transport": entry.get("transport", "streamable_http"),
        }
        if "port" in entry:
            parsed["port"] = entry["port"]
        if "env" in entry:
            parsed["env"] = entry["env"]
        if "args" in entry:
            parsed["args"] = entry["args"]

        results.append(parsed)

    return results


def catalog_entry_to_resource(
    entry: dict[str, Any],
    user_id: str = "system",
) -> McpServerResource:
    """Convert a parsed catalog entry to a McpServerResource."""
    transport = entry.get("transport", "streamable_http")
    port = entry.get("port")
    docker_ports = {}
    if port:
        docker_ports = {f"{port}/tcp": port}

    return McpServerResource(
        name=entry["name"],
        transport_type=transport,
        created_by=user_id,
        docker_image=entry.get("image"),
        docker_ports=docker_ports,
        env=entry.get("env", {}),
        args=entry.get("args", []),
        is_enabled=True,
    )
