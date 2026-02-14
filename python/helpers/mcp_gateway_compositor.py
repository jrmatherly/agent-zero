"""Gateway compositor for FastMCP multi-server mounting.

Composes registered MCP servers onto a main FastMCP instance using
create_proxy() and mount(). Each server gets its own namespace prefix.

Unmount uses providers.pop() as the maintainer-endorsed workaround
(no unmount() API exists — confirmed GitHub issue #2154).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastmcp import FastMCP
from fastmcp.server import create_proxy

from python.helpers.mcp_resource_store import McpServerResource

logger = logging.getLogger(__name__)


@dataclass
class _MountEntry:
    """Tracks a mounted provider's position and state."""

    name: str
    provider_index: int
    disabled: bool = False


class McpGatewayCompositor:
    """Composes registered MCP servers onto the main FastMCP instance."""

    def __init__(self, mcp_server: FastMCP) -> None:
        self._server = mcp_server
        self._mounts: dict[str, _MountEntry] = {}

    @property
    def mounted_names(self) -> set[str]:
        """Return the set of currently mounted server names."""
        return set(self._mounts.keys())

    def is_disabled(self, name: str) -> bool:
        """Check if a mounted server is currently disabled."""
        entry = self._mounts.get(name)
        return entry.disabled if entry else False

    async def mount_server(self, resource: McpServerResource) -> None:
        """Mount a registered server onto the main FastMCP instance."""
        if not resource.is_enabled:
            logger.debug("Skipping disabled resource: %s", resource.name)
            return

        if resource.name in self._mounts:
            raise ValueError(
                f"Server '{resource.name}' is already mounted. "
                "Unmount it first to re-mount."
            )

        proxy = self._create_proxy(resource)
        if proxy is None:
            return

        self._server.mount(proxy, namespace=resource.name)
        # Track the provider index (last added)
        idx = len(self._server.providers) - 1
        self._mounts[resource.name] = _MountEntry(
            name=resource.name, provider_index=idx
        )
        logger.info(
            "Mounted MCP server '%s' at namespace '%s'", resource.name, resource.name
        )

    async def unmount_server(self, name: str) -> None:
        """Remove a mounted server using providers.pop() workaround.

        IMPORTANT: FastMCP has NO unmount() API (confirmed GitHub issue #2154).
        The maintainer-endorsed approach is providers.pop(index).
        """
        entry = self._mounts.pop(name, None)
        if entry is None:
            return

        idx = entry.provider_index
        if idx < len(self._server.providers):
            self._server.providers.pop(idx)
            # Re-index remaining tracked mounts
            for e in self._mounts.values():
                if e.provider_index > idx:
                    e.provider_index -= 1
            logger.info("Unmounted MCP server '%s'", name)
        else:
            logger.warning(
                "Provider index %d out of range for '%s' — may already be removed",
                idx,
                name,
            )

    async def disable_server(self, name: str) -> None:
        """Temporarily hide a server's components without unmounting."""
        entry = self._mounts.get(name)
        if entry is None:
            return

        idx = entry.provider_index
        if idx < len(self._server.providers):
            self._server.providers[idx].disable()
            entry.disabled = True
            logger.info("Disabled MCP server '%s'", name)

    async def enable_server(self, name: str) -> None:
        """Restore a disabled server's component visibility."""
        entry = self._mounts.get(name)
        if entry is None:
            return

        idx = entry.provider_index
        if idx < len(self._server.providers):
            self._server.providers[idx].enable()
            entry.disabled = False
            logger.info("Enabled MCP server '%s'", name)

    def _create_proxy(self, resource: McpServerResource) -> FastMCP | None:
        """Create a FastMCP proxy for the given resource.

        Returns None if the resource doesn't have valid config for its type.
        """
        if resource.transport_type in ("streamable_http", "sse"):
            if not resource.url:
                logger.warning(
                    "HTTP resource '%s' has no URL — skipping", resource.name
                )
                return None
            return create_proxy(resource.url)

        if resource.transport_type == "stdio":
            if not resource.command:
                logger.warning(
                    "Stdio resource '%s' has no command — skipping", resource.name
                )
                return None
            # Use MCPConfig dict format accepted by create_proxy()
            return create_proxy(
                {
                    "mcpServers": {
                        resource.name: {
                            "command": resource.command,
                            "args": resource.args,
                            "env": resource.env,
                        }
                    }
                }
            )

        logger.warning(
            "Unsupported transport type '%s' for resource '%s' — skipping",
            resource.transport_type,
            resource.name,
        )
        return None
