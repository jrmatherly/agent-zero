# MCP Gateway Implementation

## Overview
The MCP Gateway adds connection pooling, multi-server composition, Docker-based MCP server lifecycle, unified tool registry, and identity header propagation to Apollos AI, leveraging FastMCP 3.0 provider architecture.

## Status
- **Phase 1**: Merged to main (PR #11, previously on `feat/mcp-gateway` branch)
- **Phase 2**: On branch `feat/mcp-gateway-phase2` — composition, discovery, WebUI, agent tool, health/lifecycle

## Components Implemented

### 1. MCP Connection Pool (`python/helpers/mcp_connection_pool.py`)
- `PooledConnection` dataclass: wraps MCP connection with metadata (created_at, last_used_at, in_use)
- `McpConnectionPool` class: keyed by server name, configurable max_connections (default 20)
- Methods: `acquire()` (get/create), `release()` (mark idle), `evict()` (remove+close), `health_check()`, `close_all()`
- Async-safe with `asyncio.Lock`
- Auto-evicts oldest idle connection when pool is full
- **Tests**: 7 tests in `tests/test_mcp_connection_pool.py`

### 2. MCP Resource Store (`python/helpers/mcp_resource_store.py`)
- `McpServerResource` dataclass: server metadata (name, transport_type, url, docker_image, docker_ports, required_roles, etc.)
- `McpResourceStoreBase` ABC: pluggable backend pattern (get, upsert, delete, list_all)
- `InMemoryMcpResourceStore`: thread-safe in-memory implementation for dev/single-instance
- Permission model: `can_access(user_id, roles, operation)` — creator OR mcp.admin OR matching role (read) / creator+admin only (write)
- Inspired by Microsoft MCP Gateway's IAdapterResourceStore pattern
- **Tests**: 13 tests in `tests/test_mcp_resource_store.py` (6 store + 7 permissions)

### 3. MCP Identity Headers (`python/helpers/mcp_identity.py`)
- `build_identity_headers(user)` → `{X-Mcp-UserId, X-Mcp-UserName, X-Mcp-Roles}`
- `strip_auth_headers(headers)` → removes Authorization, Cookie, X-CSRF-Token
- `prepare_proxy_headers(original, user)` → combines strip + inject
- Based on Microsoft MCP Gateway X-Mcp-* header pattern
- **Tests**: 6 tests in `tests/test_mcp_identity.py`

### 4. MCP Container Manager (`python/helpers/mcp_container_manager.py`)
- `McpContainerManager` class: Docker SDK lifecycle for MCP server containers
- Container naming: `apollos-mcp-{server_name}` prefix
- Methods: `start_server()` (create or reuse), `stop_server()` (stop+remove), `get_status()`, `get_logs()`, `list_servers()`
- Labels: `apollos.mcp.server`, `apollos.mcp.transport`, `apollos.mcp.created_by`
- Restart policy: `unless-stopped`
- Extends patterns from existing `python/helpers/docker.py`
- **Tests**: 6 tests in `tests/test_mcp_container_manager.py` (fully mocked Docker)

### 5. Gateway API Integration Tests
- 3 tests in `tests/test_mcp_gateway_api.py` validating store integration

## Phase 2 Components

### 6. Gateway Compositor (`python/helpers/mcp_gateway_compositor.py`)
- `McpGatewayCompositor` class: FastMCP 3.0 multi-server mounting via `create_proxy()`
- Methods: `mount_server()`, `unmount_server()`, `list_mounted()`, `get_app()` (returns ASGI app)
- Wired into `DynamicMcpProxy` — compositor's ASGI app serves as fallback after existing per-server routing
- Workaround for missing `unmount()` API: `providers.pop(index)` (tracked in FastMCP issue #2154)
- **Tests**: 16 tests in `tests/test_mcp_gateway_compositor.py`

### 7. Gateway Health Checker (`python/helpers/mcp_gateway_health.py`)
- `McpGatewayHealthChecker` class: orchestrates pool + Docker health monitoring
- Methods: `run_health_check()`, `check_docker_servers()`, `get_status()`
- **Tests**: 6 tests in `tests/test_mcp_gateway_health.py`

### 8. Gateway Lifecycle Hooks (`python/helpers/mcp_gateway_lifecycle.py`)
- `on_server_created()`: starts Docker container (if applicable) + mounts via compositor
- `on_server_deleted()`: unmounts from compositor + evicts pool + stops Docker container
- All operations wrapped in try/except for graceful degradation
- **Tests**: 8 tests in `tests/test_mcp_gateway_lifecycle.py`

### 9. MCP Registry Client (`python/helpers/mcp_registry_client.py`)
- Async httpx client for `registry.modelcontextprotocol.io` API
- Methods: `search()`, `search_all()` (cursor-based pagination)
- Configurable timeout (default 10s), resilient error handling
- **Tests**: 14 tests in `tests/test_mcp_registry_client.py`

### 10. Docker MCP Catalog (`python/helpers/docker_mcp_catalog.py`)
- `parse_catalog_entries()`: validates/normalizes catalog entry dicts from YAML
- `catalog_entry_to_resource()`: converts entries to McpServerResource with Docker port mapping
- Supports stdio, streamable_http, sse transports with environment variable passthrough
- **Tests**: 11 tests in `tests/test_docker_mcp_catalog.py`

### 11. Tool Index (`python/helpers/mcp_tool_index.py`)
- `McpToolIndex` class: keyword-searchable index across mounted MCP servers
- Methods: `register_tools()`, `unregister_server()`, `list_all_tools()`, `search_tools()`
- Case-insensitive search across tool name, description, and server name
- **Tests**: 12 tests in `tests/test_mcp_tool_index.py`

### 12. Gateway API Endpoints (Phase 2)
- `python/api/mcp_gateway_servers.py` — CRUD (list/create/update/delete/status) with RBAC
- `python/api/mcp_gateway_pool.py` — Connection pool status and health check
- `python/api/mcp_gateway_discover.py` — MCP Registry search proxy + server install (npm→npx, pip→uvx, docker)
- `python/api/mcp_gateway_catalog.py` — Docker MCP Catalog browse (YAML parse) + install
- **Tests**: 24+8+9 tests across API test files

### 13. Agent Discovery Tool (`python/tools/mcp_discover.py`)
- Extends `Tool` class, auto-discovered by tool system
- Actions: `search` (MCP Registry), `list` (all tools), `search_tools` (keyword search)
- Prompt template: `prompts/agent.system.tool.mcp_discover.md`

### 14. Gateway WebUI
- `webui/components/settings/mcp/gateway/mcp-gateway.html` — management UI with tabs (Servers, Discover, Docker Catalog)
- `webui/components/settings/mcp/gateway/mcp-gateway-store.js` — Alpine.js store
- Integrated into settings via `webui/components/settings/mcp/mcp-settings.html` section link

### 15. Identity Integration Tests
- 7 tests in `tests/test_mcp_identity_integration.py` — build_identity_headers, strip_auth_headers, prepare_proxy_headers

## Test Results
- Phase 1: 35 tests across 5 test files
- Phase 2: ~115 new tests across 10 test files
- Total: 749 tests passing, 2 skipped, lint/format clean

## Dependencies
- FastMCP 3.0.0rc2 (upgraded from rc1; rc2 has no API breaking changes, only CLI restructure + tag filter bugfix)
- httpx 0.28+ (for registry client; already in project)
- Docker SDK (already in project)
- No new dependencies added in Phase 2

## Coexistence Strategy
MCPConfig (agent-side, settings-driven) and McpResourceStore (gateway-side, RBAC-driven) are architecturally independent. MCPConfig manages servers the agent connects to; McpResourceStore manages servers the gateway exposes. The compositor reads from the resource store; MCPConfig continues managing agent-side servers from settings.

## Future Phases (Not Yet Implemented)
- FAISS-based semantic tool search across registered MCP servers
- Redis-backed resource store for horizontal scaling
- Gateway federation (IBM ContextForge pattern)
- Kubernetes-native deployment (Microsoft MCP Gateway pattern)
- Agent-as-Tool: Expose Apollos AI agents as MCP servers to other frameworks

## Research Sources
- `.scratchpad/microsoft-mcp-gateway-validation-report.md`
- `.scratchpad/mcp-gateway-phase2-plan.md`
- Plan: `docs/plans/2026-02-13-mcp-gateway.md`
