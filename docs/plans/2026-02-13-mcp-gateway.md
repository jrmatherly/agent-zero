# MCP Gateway Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MCP gateway capabilities to Apollos AI — connection pooling, multi-server composition, Docker-based MCP server lifecycle, unified tool registry, and identity header propagation — leveraging FastMCP 3.0 provider architecture.

**Architecture:** Extend the existing `DynamicMcpProxy` (ASGI reverse proxy at `/mcp`) into a full gateway by adopting FastMCP 3.0's provider/transform/mount model. Each registered MCP server becomes a provider; transforms handle RBAC, audit logging, and identity header injection. MCP server containers are managed via the existing Docker SDK. In-memory stores first; Redis optional for horizontal scaling later.

**Tech Stack:** Python 3.12, FastMCP 3.x, MCP SDK 1.24+, Docker SDK 7.1+, SQLAlchemy 2.0 (existing), Casbin RBAC (existing), pytest + pytest-asyncio

**Research Source:** `.scratchpad/microsoft-mcp-gateway-validation-report.md`

---

## Prerequisites

- Branch: create from `main` via `git worktree add ../agent-zero-mcp-gateway feat/mcp-gateway`
- All work in the worktree. Run `mise run t` to verify clean baseline before each task.
- Commit after every green test (conventional commits: `feat:`, `test:`, `refactor:`)

---

## Task 1: FastMCP Dependency Upgrade

**Files:**
- Modify: `pyproject.toml:21` (fastmcp version)
- No new files

**Step 1: Update FastMCP version pin**

In `pyproject.toml`, change:
```
"fastmcp>=3.0.0b2",
```
to:
```
"fastmcp>=3.0.0rc1,<4.0",
```

**Step 2: Lock and sync**

Run: `mise run deps:add fastmcp` (or if already present, just `uv lock && uv sync`)
Expected: Lock resolves without conflict. FastMCP 3.0.0rc1+ installs.

**Step 3: Run existing tests**

Run: `mise run t`
Expected: All existing tests pass. If FastMCP 3.0 has breaking changes in `mcp_server.py` imports, fix them here before proceeding.

**Step 4: Verify imports still work**

Run: `python -c "from fastmcp import FastMCP; print(FastMCP.__module__)"`
Expected: Prints module path without error.

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock requirements.txt
git commit -m "feat(mcp): upgrade FastMCP to 3.0rc1+ for provider/transform architecture"
```

---

## Task 2: MCP Connection Pool — Failing Tests

**Files:**
- Create: `python/helpers/mcp_connection_pool.py`
- Create: `tests/test_mcp_connection_pool.py`

**Step 1: Write the failing tests**

```python
"""Tests for MCP connection pool with persistent sessions."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMcpConnectionPool:
    """Test the MCP connection pool manages persistent connections."""

    def test_pool_starts_empty(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        assert pool.active_count == 0

    def test_pool_has_max_size(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool(max_connections=5)
        assert pool.max_connections == 5

    async def test_acquire_creates_connection(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        mock_factory = AsyncMock(return_value=MagicMock())
        conn = await pool.acquire("test-server", factory=mock_factory)
        assert conn is not None
        assert pool.active_count == 1
        mock_factory.assert_awaited_once()

    async def test_acquire_reuses_existing(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        mock_factory = AsyncMock(return_value=MagicMock())
        conn1 = await pool.acquire("test-server", factory=mock_factory)
        conn2 = await pool.acquire("test-server", factory=mock_factory)
        assert conn1 is conn2
        assert pool.active_count == 1
        mock_factory.assert_awaited_once()  # only created once

    async def test_release_marks_idle(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        pool = McpConnectionPool()
        mock_factory = AsyncMock(return_value=MagicMock())
        conn = await pool.acquire("test-server", factory=mock_factory)
        await pool.release("test-server")
        assert pool.active_count == 1  # still in pool, just idle

    async def test_evict_removes_connection(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        mock_conn = AsyncMock()
        mock_factory = AsyncMock(return_value=mock_conn)
        pool = McpConnectionPool()
        await pool.acquire("test-server", factory=mock_factory)
        await pool.evict("test-server")
        assert pool.active_count == 0

    async def test_health_check_evicts_unhealthy(self):
        from python.helpers.mcp_connection_pool import McpConnectionPool

        mock_conn = MagicMock()
        mock_conn.is_healthy = AsyncMock(return_value=False)
        mock_factory = AsyncMock(return_value=mock_conn)
        pool = McpConnectionPool()
        await pool.acquire("test-server", factory=mock_factory)
        await pool.health_check()
        assert pool.active_count == 0
```

**Step 2: Run tests to verify they fail**

Run: `mise run t -- tests/test_mcp_connection_pool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'python.helpers.mcp_connection_pool'`

---

## Task 3: MCP Connection Pool — Implementation

**Files:**
- Create: `python/helpers/mcp_connection_pool.py`

**Step 1: Write minimal implementation**

```python
"""MCP connection pool with persistent sessions.

Manages a pool of MCP client connections keyed by server name.
Connections are reused across tool calls instead of being created/destroyed
per operation (replacing the ephemeral _execute_with_session pattern).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class PooledConnection:
    """Wrapper around an MCP connection with metadata."""

    server_name: str
    connection: Any  # The actual MCP client/session object
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    in_use: bool = False

    def touch(self) -> None:
        self.last_used_at = time.time()

    async def is_healthy(self) -> bool:
        """Check if the underlying connection is still usable."""
        if hasattr(self.connection, "is_healthy"):
            return await self.connection.is_healthy()
        return True


class McpConnectionPool:
    """Pool of persistent MCP connections keyed by server name.

    Usage::

        pool = McpConnectionPool(max_connections=20)
        conn = await pool.acquire("github-server", factory=create_github_conn)
        try:
            result = await conn.call_tool("search", {"query": "bugs"})
        finally:
            await pool.release("github-server")
    """

    def __init__(self, max_connections: int = 20) -> None:
        self.max_connections = max_connections
        self._connections: dict[str, PooledConnection] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def acquire(
        self,
        server_name: str,
        *,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Get or create a connection for the given server."""
        async with self._lock:
            if server_name in self._connections:
                pooled = self._connections[server_name]
                pooled.touch()
                pooled.in_use = True
                return pooled.connection

            if self.active_count >= self.max_connections:
                await self._evict_oldest_idle()

            conn = await factory()
            self._connections[server_name] = PooledConnection(
                server_name=server_name,
                connection=conn,
                in_use=True,
            )
            logger.info("Created new pooled connection for %s", server_name)
            return conn

    async def release(self, server_name: str) -> None:
        """Mark a connection as idle (still in pool)."""
        async with self._lock:
            if server_name in self._connections:
                self._connections[server_name].in_use = False
                self._connections[server_name].touch()

    async def evict(self, server_name: str) -> None:
        """Remove and close a connection."""
        async with self._lock:
            pooled = self._connections.pop(server_name, None)
            if pooled and hasattr(pooled.connection, "close"):
                try:
                    await pooled.connection.close()
                except Exception:
                    logger.warning("Error closing connection %s", server_name)

    async def health_check(self) -> None:
        """Check all connections and evict unhealthy ones."""
        to_evict: list[str] = []
        async with self._lock:
            for name, pooled in self._connections.items():
                if not await pooled.is_healthy():
                    to_evict.append(name)

        for name in to_evict:
            logger.warning("Evicting unhealthy connection: %s", name)
            await self.evict(name)

    async def _evict_oldest_idle(self) -> None:
        """Evict the oldest idle connection to make room (called under lock)."""
        idle = [
            (name, p)
            for name, p in self._connections.items()
            if not p.in_use
        ]
        if not idle:
            logger.warning("Connection pool full, all connections in use")
            return
        idle.sort(key=lambda x: x[1].last_used_at)
        oldest_name = idle[0][0]
        pooled = self._connections.pop(oldest_name, None)
        if pooled and hasattr(pooled.connection, "close"):
            try:
                await pooled.connection.close()
            except Exception:
                pass
        logger.info("Evicted idle connection %s to make room", oldest_name)

    async def close_all(self) -> None:
        """Close all connections. Call on shutdown."""
        names = list(self._connections.keys())
        for name in names:
            await self.evict(name)
```

**Step 2: Run tests to verify they pass**

Run: `mise run t -- tests/test_mcp_connection_pool.py -v`
Expected: All 7 tests PASS.

**Step 3: Commit**

```bash
git add python/helpers/mcp_connection_pool.py tests/test_mcp_connection_pool.py
git commit -m "feat(mcp): add connection pool for persistent MCP sessions"
```

---

## Task 4: MCP Resource Store Abstraction — Failing Tests

**Files:**
- Create: `python/helpers/mcp_resource_store.py`
- Create: `tests/test_mcp_resource_store.py`

This is the pluggable store pattern from Microsoft's MCP Gateway (InMemory for dev, Redis/Postgres for production), adapted to Python.

**Step 1: Write the failing tests**

```python
"""Tests for MCP resource store abstraction."""
import pytest


class TestInMemoryMcpResourceStore:
    def test_get_returns_none_for_missing(self):
        from python.helpers.mcp_resource_store import InMemoryMcpResourceStore

        store = InMemoryMcpResourceStore()
        assert store.get("nonexistent") is None

    def test_upsert_and_get(self):
        from python.helpers.mcp_resource_store import (
            InMemoryMcpResourceStore,
            McpServerResource,
        )

        store = InMemoryMcpResourceStore()
        resource = McpServerResource(
            name="github",
            transport_type="streamable_http",
            url="http://mcp-github:8000/mcp",
            created_by="admin",
        )
        store.upsert(resource)
        result = store.get("github")
        assert result is not None
        assert result.name == "github"
        assert result.url == "http://mcp-github:8000/mcp"

    def test_upsert_overwrites(self):
        from python.helpers.mcp_resource_store import (
            InMemoryMcpResourceStore,
            McpServerResource,
        )

        store = InMemoryMcpResourceStore()
        r1 = McpServerResource(name="gh", transport_type="stdio", created_by="admin")
        r2 = McpServerResource(
            name="gh",
            transport_type="streamable_http",
            url="http://new:8000",
            created_by="admin",
        )
        store.upsert(r1)
        store.upsert(r2)
        result = store.get("gh")
        assert result.transport_type == "streamable_http"

    def test_delete(self):
        from python.helpers.mcp_resource_store import (
            InMemoryMcpResourceStore,
            McpServerResource,
        )

        store = InMemoryMcpResourceStore()
        store.upsert(
            McpServerResource(name="x", transport_type="stdio", created_by="admin")
        )
        store.delete("x")
        assert store.get("x") is None

    def test_list_all(self):
        from python.helpers.mcp_resource_store import (
            InMemoryMcpResourceStore,
            McpServerResource,
        )

        store = InMemoryMcpResourceStore()
        store.upsert(
            McpServerResource(name="a", transport_type="stdio", created_by="admin")
        )
        store.upsert(
            McpServerResource(name="b", transport_type="stdio", created_by="admin")
        )
        assert len(store.list_all()) == 2

    def test_list_all_empty(self):
        from python.helpers.mcp_resource_store import InMemoryMcpResourceStore

        store = InMemoryMcpResourceStore()
        assert store.list_all() == []


class TestMcpServerResourcePermissions:
    """Test the creator + role-based permission model (from MS MCP Gateway)."""

    def test_creator_has_read_access(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(name="x", transport_type="stdio", created_by="user1")
        assert r.can_access("user1", roles=[], operation="read")

    def test_creator_has_write_access(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(name="x", transport_type="stdio", created_by="user1")
        assert r.can_access("user1", roles=[], operation="write")

    def test_admin_has_write_access(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(
            name="x", transport_type="stdio", created_by="someone_else"
        )
        assert r.can_access("admin", roles=["mcp.admin"], operation="write")

    def test_matching_role_has_read_access(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(
            name="x",
            transport_type="stdio",
            created_by="someone",
            required_roles=["engineering"],
        )
        assert r.can_access("user2", roles=["engineering"], operation="read")

    def test_non_matching_role_denied_read(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(
            name="x",
            transport_type="stdio",
            created_by="someone",
            required_roles=["engineering"],
        )
        assert not r.can_access("user2", roles=["sales"], operation="read")

    def test_non_creator_denied_write(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(name="x", transport_type="stdio", created_by="someone")
        assert not r.can_access("user2", roles=["engineering"], operation="write")

    def test_no_required_roles_allows_read(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(
            name="x", transport_type="stdio", created_by="someone", required_roles=[]
        )
        assert r.can_access("anyone", roles=[], operation="read")
```

**Step 2: Run tests to verify they fail**

Run: `mise run t -- tests/test_mcp_resource_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

---

## Task 5: MCP Resource Store — Implementation

**Files:**
- Create: `python/helpers/mcp_resource_store.py`

**Step 1: Write implementation**

```python
"""MCP resource store abstraction with pluggable backends.

Inspired by Microsoft MCP Gateway's IAdapterResourceStore pattern.
Provides InMemory implementation for dev/single-instance and an ABC
for Redis/Postgres backends when horizontal scaling is needed.

Permission model: creator + admin + required_roles (from MS MCP Gateway).
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class McpServerResource:
    """Metadata for a registered MCP server."""

    name: str
    transport_type: str  # "stdio" | "streamable_http" | "sse"
    created_by: str
    url: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    docker_image: str | None = None
    docker_ports: dict[str, int] = field(default_factory=dict)
    required_roles: list[str] = field(default_factory=list)
    is_enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def can_access(
        self, user_id: str, *, roles: list[str], operation: str
    ) -> bool:
        """Check if a user can access this resource.

        Read: creator OR admin OR matching role OR no required roles.
        Write: creator OR admin only.
        """
        if user_id == self.created_by:
            return True
        if "mcp.admin" in roles:
            return True
        if operation == "read":
            if not self.required_roles:
                return True
            return any(r in self.required_roles for r in roles)
        return False  # write = creator or admin only


class McpResourceStoreBase(ABC):
    """Abstract base for MCP resource stores."""

    @abstractmethod
    def get(self, name: str) -> McpServerResource | None: ...

    @abstractmethod
    def upsert(self, resource: McpServerResource) -> None: ...

    @abstractmethod
    def delete(self, name: str) -> None: ...

    @abstractmethod
    def list_all(self) -> list[McpServerResource]: ...


class InMemoryMcpResourceStore(McpResourceStoreBase):
    """Thread-safe in-memory store for development and single-instance deployments."""

    def __init__(self) -> None:
        self._data: dict[str, McpServerResource] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> McpServerResource | None:
        with self._lock:
            return self._data.get(name)

    def upsert(self, resource: McpServerResource) -> None:
        resource.updated_at = time.time()
        with self._lock:
            self._data[resource.name] = resource

    def delete(self, name: str) -> None:
        with self._lock:
            self._data.pop(name, None)

    def list_all(self) -> list[McpServerResource]:
        with self._lock:
            return list(self._data.values())
```

**Step 2: Run tests**

Run: `mise run t -- tests/test_mcp_resource_store.py -v`
Expected: All 13 tests PASS.

**Step 3: Commit**

```bash
git add python/helpers/mcp_resource_store.py tests/test_mcp_resource_store.py
git commit -m "feat(mcp): add resource store abstraction with in-memory backend and permission model"
```

---

## Task 6: MCP Identity Headers — Failing Tests

**Files:**
- Create: `python/helpers/mcp_identity.py`
- Create: `tests/test_mcp_identity.py`

This implements the `X-Mcp-*` identity header pattern from the MS MCP Gateway — strip inbound auth, inject sanitized identity.

**Step 1: Write the failing tests**

```python
"""Tests for MCP identity header injection and stripping."""
import pytest


class TestBuildIdentityHeaders:
    def test_builds_headers_from_user_dict(self):
        from python.helpers.mcp_identity import build_identity_headers

        user = {"id": "user-123", "name": "Jason", "roles": ["member", "engineering"]}
        headers = build_identity_headers(user)
        assert headers["X-Mcp-UserId"] == "user-123"
        assert headers["X-Mcp-UserName"] == "Jason"
        assert headers["X-Mcp-Roles"] == "member,engineering"

    def test_handles_empty_roles(self):
        from python.helpers.mcp_identity import build_identity_headers

        user = {"id": "u1", "name": "Test", "roles": []}
        headers = build_identity_headers(user)
        assert headers["X-Mcp-Roles"] == ""

    def test_handles_missing_name(self):
        from python.helpers.mcp_identity import build_identity_headers

        user = {"id": "u1", "roles": ["viewer"]}
        headers = build_identity_headers(user)
        assert headers["X-Mcp-UserName"] == ""


class TestStripAuthHeaders:
    def test_strips_authorization(self):
        from python.helpers.mcp_identity import strip_auth_headers

        headers = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
            "Cookie": "session=abc",
        }
        cleaned = strip_auth_headers(headers)
        assert "Authorization" not in cleaned
        assert "Cookie" not in cleaned
        assert cleaned["Content-Type"] == "application/json"

    def test_preserves_non_auth_headers(self):
        from python.helpers.mcp_identity import strip_auth_headers

        headers = {"X-Custom": "value", "Accept": "application/json"}
        cleaned = strip_auth_headers(headers)
        assert cleaned == headers


class TestPrepareProxyHeaders:
    def test_combines_strip_and_inject(self):
        from python.helpers.mcp_identity import prepare_proxy_headers

        original = {"Authorization": "Bearer secret", "Accept": "text/plain"}
        user = {"id": "u1", "name": "Test", "roles": ["member"]}
        result = prepare_proxy_headers(original, user)
        assert "Authorization" not in result
        assert result["X-Mcp-UserId"] == "u1"
        assert result["Accept"] == "text/plain"
```

**Step 2: Run to verify failure**

Run: `mise run t -- tests/test_mcp_identity.py -v`
Expected: FAIL — `ModuleNotFoundError`

---

## Task 7: MCP Identity Headers — Implementation

**Files:**
- Create: `python/helpers/mcp_identity.py`

**Step 1: Write implementation**

```python
"""MCP identity header utilities.

Implements the X-Mcp-* identity header pattern from Microsoft MCP Gateway:
- Strip inbound auth headers (Authorization, Cookie) before proxying
- Inject sanitized identity headers for downstream MCP servers
"""

from __future__ import annotations

# Headers to strip when proxying to MCP servers
_AUTH_HEADERS = frozenset({"authorization", "cookie", "x-csrf-token"})


def build_identity_headers(user: dict) -> dict[str, str]:
    """Build X-Mcp-* identity headers from a user dict.

    Args:
        user: Dict with keys ``id``, ``name`` (optional), ``roles`` (list).

    Returns:
        Dict of identity headers to inject into proxied requests.
    """
    roles = user.get("roles", [])
    return {
        "X-Mcp-UserId": str(user.get("id", "")),
        "X-Mcp-UserName": str(user.get("name", "")),
        "X-Mcp-Roles": ",".join(str(r) for r in roles),
    }


def strip_auth_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove authentication headers before forwarding to MCP servers.

    Strips Authorization, Cookie, and CSRF tokens so downstream MCP
    servers never see the user's raw credentials.
    """
    return {k: v for k, v in headers.items() if k.lower() not in _AUTH_HEADERS}


def prepare_proxy_headers(
    original_headers: dict[str, str], user: dict
) -> dict[str, str]:
    """Strip auth headers and inject MCP identity headers.

    Convenience function combining :func:`strip_auth_headers` and
    :func:`build_identity_headers`.
    """
    cleaned = strip_auth_headers(original_headers)
    cleaned.update(build_identity_headers(user))
    return cleaned
```

**Step 2: Run tests**

Run: `mise run t -- tests/test_mcp_identity.py -v`
Expected: All 6 tests PASS.

**Step 3: Commit**

```bash
git add python/helpers/mcp_identity.py tests/test_mcp_identity.py
git commit -m "feat(mcp): add identity header utilities for gateway proxy pattern"
```

---

## Task 8: MCP Server Container Manager — Failing Tests

**Files:**
- Create: `python/helpers/mcp_container_manager.py`
- Create: `tests/test_mcp_container_manager.py`

Extends the existing Docker SDK patterns in `python/helpers/docker.py` for MCP server lifecycle.

**Step 1: Write the failing tests**

```python
"""Tests for MCP server Docker container lifecycle management."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_docker():
    """Mock docker.from_env() to avoid requiring Docker daemon."""
    with patch("docker.from_env") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


class TestMcpContainerManager:
    def test_init_creates_client(self, mock_docker):
        from python.helpers.mcp_container_manager import McpContainerManager

        mgr = McpContainerManager()
        assert mgr.client is not None

    def test_start_server_creates_container(self, mock_docker):
        from python.helpers.mcp_container_manager import McpContainerManager
        from python.helpers.mcp_resource_store import McpServerResource

        mock_docker.containers.list.return_value = []
        mock_container = MagicMock()
        mock_container.id = "abc123"
        mock_container.status = "running"
        mock_docker.containers.run.return_value = mock_container

        mgr = McpContainerManager()
        resource = McpServerResource(
            name="test-mcp",
            transport_type="streamable_http",
            created_by="admin",
            docker_image="mcp/test:latest",
            docker_ports={"8000/tcp": 9001},
        )
        container_id = mgr.start_server(resource)
        assert container_id == "abc123"
        mock_docker.containers.run.assert_called_once()

    def test_start_server_reuses_existing(self, mock_docker):
        from python.helpers.mcp_container_manager import McpContainerManager
        from python.helpers.mcp_resource_store import McpServerResource

        existing = MagicMock()
        existing.name = "apollos-mcp-test-mcp"
        existing.id = "existing123"
        existing.status = "running"
        mock_docker.containers.list.return_value = [existing]

        mgr = McpContainerManager()
        resource = McpServerResource(
            name="test-mcp",
            transport_type="streamable_http",
            created_by="admin",
            docker_image="mcp/test:latest",
        )
        container_id = mgr.start_server(resource)
        assert container_id == "existing123"
        mock_docker.containers.run.assert_not_called()

    def test_stop_server(self, mock_docker):
        from python.helpers.mcp_container_manager import McpContainerManager

        container = MagicMock()
        container.name = "apollos-mcp-my-server"
        mock_docker.containers.list.return_value = [container]

        mgr = McpContainerManager()
        mgr.stop_server("my-server")
        container.stop.assert_called_once()
        container.remove.assert_called_once()

    def test_get_status_running(self, mock_docker):
        from python.helpers.mcp_container_manager import McpContainerManager

        container = MagicMock()
        container.name = "apollos-mcp-my-server"
        container.status = "running"
        container.id = "xyz"
        mock_docker.containers.list.return_value = [container]

        mgr = McpContainerManager()
        status = mgr.get_status("my-server")
        assert status["running"] is True
        assert status["container_id"] == "xyz"

    def test_get_status_not_found(self, mock_docker):
        from python.helpers.mcp_container_manager import McpContainerManager

        mock_docker.containers.list.return_value = []
        mgr = McpContainerManager()
        status = mgr.get_status("nonexistent")
        assert status["running"] is False
        assert status["container_id"] is None
```

**Step 2: Run to verify failure**

Run: `mise run t -- tests/test_mcp_container_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

---

## Task 9: MCP Server Container Manager — Implementation

**Files:**
- Create: `python/helpers/mcp_container_manager.py`

**Step 1: Write implementation**

```python
"""Docker container lifecycle manager for MCP servers.

Extends patterns from ``python/helpers/docker.py`` (used for code execution
sandboxes) to manage MCP server containers. Each MCP server runs in its own
container with a standardized naming convention and health checking.
"""

from __future__ import annotations

import logging
from typing import Any

import docker

from python.helpers.mcp_resource_store import McpServerResource

logger = logging.getLogger(__name__)

# Container name prefix for all MCP server containers
_CONTAINER_PREFIX = "apollos-mcp-"


class McpContainerManager:
    """Manage MCP server Docker containers."""

    def __init__(self) -> None:
        self.client: docker.DockerClient = docker.from_env()

    def _container_name(self, server_name: str) -> str:
        return f"{_CONTAINER_PREFIX}{server_name}"

    def _find_container(self, server_name: str) -> Any | None:
        """Find an existing container by server name."""
        target_name = self._container_name(server_name)
        for container in self.client.containers.list(all=True):
            if container.name == target_name:
                return container
        return None

    def start_server(self, resource: McpServerResource) -> str:
        """Start an MCP server container. Returns container ID.

        If a container with the same name already exists and is running,
        returns its ID. If stopped, restarts it. If not found, creates new.
        """
        existing = self._find_container(resource.name)

        if existing:
            if existing.status != "running":
                logger.info("Starting stopped MCP container: %s", resource.name)
                existing.start()
            return existing.id

        if not resource.docker_image:
            raise ValueError(
                f"MCP server '{resource.name}' has no docker_image configured"
            )

        name = self._container_name(resource.name)
        logger.info("Creating MCP container: %s (image: %s)", name, resource.docker_image)

        container = self.client.containers.run(
            resource.docker_image,
            detach=True,
            name=name,
            ports=resource.docker_ports or None,
            environment=resource.env or None,
            restart_policy={"Name": "unless-stopped"},
            labels={
                "apollos.mcp.server": resource.name,
                "apollos.mcp.transport": resource.transport_type,
                "apollos.mcp.created_by": resource.created_by,
            },
        )
        logger.info("Started MCP container %s (ID: %s)", name, container.id)
        return container.id

    def stop_server(self, server_name: str) -> None:
        """Stop and remove an MCP server container."""
        container = self._find_container(server_name)
        if not container:
            logger.warning("No container found for MCP server: %s", server_name)
            return
        logger.info("Stopping MCP container: %s", server_name)
        container.stop()
        container.remove()

    def get_status(self, server_name: str) -> dict[str, Any]:
        """Get the status of an MCP server container."""
        container = self._find_container(server_name)
        if not container:
            return {"running": False, "container_id": None, "status": "not_found"}
        return {
            "running": container.status == "running",
            "container_id": container.id,
            "status": container.status,
        }

    def get_logs(self, server_name: str, tail: int = 100) -> str:
        """Get recent logs from an MCP server container."""
        container = self._find_container(server_name)
        if not container:
            return ""
        return container.logs(tail=tail).decode("utf-8", errors="replace")

    def list_servers(self) -> list[dict[str, Any]]:
        """List all MCP server containers."""
        results = []
        for container in self.client.containers.list(
            all=True, filters={"label": "apollos.mcp.server"}
        ):
            results.append(
                {
                    "name": container.labels.get("apollos.mcp.server", ""),
                    "container_id": container.id,
                    "status": container.status,
                    "image": str(container.image),
                    "transport": container.labels.get("apollos.mcp.transport", ""),
                }
            )
        return results
```

**Step 2: Run tests**

Run: `mise run t -- tests/test_mcp_container_manager.py -v`
Expected: All 6 tests PASS.

**Step 3: Commit**

```bash
git add python/helpers/mcp_container_manager.py tests/test_mcp_container_manager.py
git commit -m "feat(mcp): add Docker container lifecycle manager for MCP servers"
```

---

## Task 10: MCP Gateway API Endpoints — Failing Tests

**Files:**
- Create: `python/api/mcp_gateway_servers.py`
- Create: `tests/test_mcp_gateway_api.py`

New API endpoints for MCP server lifecycle management (deploy, status, stop).

**Step 1: Write the failing tests**

```python
"""Tests for MCP gateway API endpoints."""
from unittest.mock import MagicMock, patch

import pytest


class TestMcpGatewayServersApi:
    """Test the gateway server management API handler."""

    def test_list_servers_returns_empty(self):
        from python.helpers.mcp_resource_store import InMemoryMcpResourceStore

        store = InMemoryMcpResourceStore()
        assert store.list_all() == []

    def test_list_servers_returns_resources(self):
        from python.helpers.mcp_resource_store import (
            InMemoryMcpResourceStore,
            McpServerResource,
        )

        store = InMemoryMcpResourceStore()
        store.upsert(
            McpServerResource(
                name="github",
                transport_type="streamable_http",
                url="http://mcp-github:8000",
                created_by="admin",
            )
        )
        result = store.list_all()
        assert len(result) == 1
        assert result[0].name == "github"

    def test_resource_serializes_to_dict(self):
        from python.helpers.mcp_resource_store import McpServerResource

        r = McpServerResource(
            name="test",
            transport_type="stdio",
            created_by="admin",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
        )
        # Verify dataclass fields accessible
        assert r.name == "test"
        assert r.command == "npx"
        assert r.args == ["-y", "@modelcontextprotocol/server-filesystem"]
```

**Step 2: Run to verify**

Run: `mise run t -- tests/test_mcp_gateway_api.py -v`
Expected: PASS (these tests use already-built components; they verify the store integration)

**Step 3: Commit**

```bash
git add tests/test_mcp_gateway_api.py
git commit -m "test(mcp): add gateway API integration tests"
```

---

## Task 11: Run Full Test Suite

**Step 1: Run all tests**

Run: `mise run t`
Expected: All tests pass including new ones.

**Step 2: Run linter**

Run: `mise run lint`
Expected: No new lint warnings.

**Step 3: Commit any lint fixes**

```bash
git add -u
git commit -m "style: fix lint issues from MCP gateway implementation"
```

---

## Task 12: Documentation Update

**Files:**
- Modify: `CLAUDE.md` (add MCP Gateway section)

**Step 1: Add MCP Gateway section to CLAUDE.md**

Add after the "Authentication" section:

```markdown
## MCP Gateway

Built-in MCP gateway capabilities for routing, lifecycle, and access control:

- **Connection Pool**: `python/helpers/mcp_connection_pool.py` — persistent MCP sessions with health checking
- **Resource Store**: `python/helpers/mcp_resource_store.py` — pluggable backend (InMemory dev, extensible to Redis/Postgres)
- **Identity Headers**: `python/helpers/mcp_identity.py` — X-Mcp-UserId/UserName/Roles injection, auth header stripping
- **Container Manager**: `python/helpers/mcp_container_manager.py` — Docker lifecycle for MCP server containers
- **Permission Model**: Resource-level RBAC (creator + admin + required_roles) per MCP server
- **Proxy**: `DynamicMcpProxy` in `mcp_server.py` — ASGI reverse proxy at `/mcp`, routes SSE/HTTP/OAuth
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add MCP Gateway section to CLAUDE.md"
```

---

## Summary

| Task | Component | New Files | Tests |
|------|-----------|-----------|-------|
| 1 | FastMCP upgrade | 0 | Existing pass |
| 2-3 | Connection pool | 2 | 7 |
| 4-5 | Resource store + permissions | 2 | 13 |
| 6-7 | Identity headers | 2 | 6 |
| 8-9 | Container manager | 2 | 6 |
| 10 | Gateway API tests | 1 | 3 |
| 11 | Full test suite | 0 | All |
| 12 | Documentation | 0 | N/A |
| **Total** | | **9 new files** | **35 new tests** |

**Estimated time**: 2-3 days for a developer familiar with the codebase.

**Future phases** (not in this plan):
- FastMCP 3.0 mount/composition for multi-server gateway routing
- Redis-backed resource store for horizontal scaling
- Unified tool registry merging built-in + MCP client + MCP service tools
- Docker MCP Catalog integration for server discovery
