# MCP Gateway Implementation

## Overview
The MCP Gateway adds connection pooling, multi-server composition, Docker-based MCP server lifecycle, unified tool registry, and identity header propagation to Apollos AI, leveraging FastMCP 3.0 provider architecture.

## Branch
- **Feature branch**: `feat/mcp-gateway` (7 commits, 826 lines added)
- **Base**: `main` at `f41ea36` (v0.4.0)
- **Worktree**: `.worktrees/mcp-gateway`

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

## Test Results
- **635 passed**, 1 skipped, 21 warnings
- 35 new tests total
- Lint clean (Ruff + Biome)
- Format clean

## Dependencies
- FastMCP 3.0.0rc1 (upgraded on main before branching)
- Docker SDK (already in project)
- No new dependencies added

## Future Phases (Not Yet Implemented)
- FastMCP 3.0 mount/composition for multi-server gateway routing
- Redis-backed resource store for horizontal scaling
- Unified tool registry merging built-in + MCP client + MCP service tools
- Docker MCP Catalog integration for server discovery

## Research Source
- `.scratchpad/microsoft-mcp-gateway-validation-report.md`
- Plan: `docs/plans/2026-02-13-mcp-gateway.md`
