"""MCP Gateway Docker Catalog API — browse and install from Docker MCP Catalog.

Supports YAML import of Docker MCP Catalog entries and
conversion to gateway-managed McpServerResource objects.
"""

import json
import logging
from typing import Any

import yaml

from python.helpers.api import ApiHandler, Request, Response
from python.helpers.docker_mcp_catalog import (
    catalog_entry_to_resource,
    parse_catalog_entries,
)

logger = logging.getLogger(__name__)


def handle_browse(catalog_yaml: str) -> dict[str, Any]:
    """Parse YAML content and return browsable catalog entries."""
    try:
        data = yaml.safe_load(catalog_yaml)
    except yaml.YAMLError as exc:
        return {"ok": False, "error": f"Invalid YAML: {exc}"}

    if isinstance(data, dict):
        entries = data.get("servers", [])
    elif isinstance(data, list):
        entries = data
    else:
        return {"ok": False, "error": "Expected YAML with 'servers' list or array"}

    parsed = parse_catalog_entries(entries)
    return {"ok": True, "data": parsed}


def handle_install(
    store,
    user_id: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Install a Docker catalog entry as a McpServerResource."""
    if not entry.get("name"):
        return {"ok": False, "error": "Missing required field: name"}

    resource = catalog_entry_to_resource(entry, user_id=user_id)
    store.upsert(resource)

    from python.api.mcp_gateway_servers import resource_to_dict

    return {"ok": True, "data": resource_to_dict(resource)}


class McpGatewayCatalog(ApiHandler):
    """API for browsing and installing from Docker MCP Catalog."""

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return None

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action", "browse")
        user_id = self._get_user_id() or "anonymous"

        if action == "browse":
            catalog_yaml = input.get("yaml", "")
            if not catalog_yaml:
                return {"ok": False, "error": "Missing required field: yaml"}
            return handle_browse(catalog_yaml)

        elif action == "install":
            from python.api.mcp_gateway_servers import get_store

            store = get_store()
            entry = input.get("entry", {})
            return handle_install(store=store, user_id=user_id, entry=entry)

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
