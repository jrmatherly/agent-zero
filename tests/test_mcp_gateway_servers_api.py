"""Tests for MCP Gateway Servers CRUD API handler.

Tests the McpGatewayServers API handler that manages McpServerResource
objects through the InMemoryMcpResourceStore.
"""

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Fresh in-memory resource store for each test."""
    from python.helpers.mcp_resource_store import InMemoryMcpResourceStore

    return InMemoryMcpResourceStore()


@pytest.fixture
def sample_resource():
    """A sample McpServerResource for testing."""
    from python.helpers.mcp_resource_store import McpServerResource

    return McpServerResource(
        name="github",
        transport_type="streamable_http",
        url="http://mcp-github:8000/mcp",
        created_by="user1",
    )


@pytest.fixture
def sample_stdio_resource():
    """A sample stdio McpServerResource for testing."""
    from python.helpers.mcp_resource_store import McpServerResource

    return McpServerResource(
        name="filesystem",
        transport_type="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"],
        created_by="user1",
    )


# ---------------------------------------------------------------------------
# Handler import and class structure
# ---------------------------------------------------------------------------


class TestHandlerStructure:
    """Verify the handler class exists and follows ApiHandler conventions."""

    def test_handler_is_api_handler_subclass(self):
        from python.api.mcp_gateway_servers import McpGatewayServers
        from python.helpers.api import ApiHandler

        assert issubclass(McpGatewayServers, ApiHandler)

    def test_handler_declares_write_permission(self):
        from python.api.mcp_gateway_servers import McpGatewayServers

        # Handler returns None (handles RBAC dynamically like mcp_services.py)
        # or returns a specific permission tuple
        perm = McpGatewayServers.get_required_permission()
        # Dynamic RBAC: None means handled in process()
        assert perm is None


# ---------------------------------------------------------------------------
# Resource serialization
# ---------------------------------------------------------------------------


class TestResourceSerialization:
    """Test resource_to_dict helper."""

    def test_serializes_all_fields(self, sample_resource):
        from python.api.mcp_gateway_servers import resource_to_dict

        d = resource_to_dict(sample_resource)
        assert d["name"] == "github"
        assert d["transport_type"] == "streamable_http"
        assert d["url"] == "http://mcp-github:8000/mcp"
        assert d["created_by"] == "user1"
        assert d["is_enabled"] is True
        assert "created_at" in d
        assert "updated_at" in d

    def test_serializes_stdio_fields(self, sample_stdio_resource):
        from python.api.mcp_gateway_servers import resource_to_dict

        d = resource_to_dict(sample_stdio_resource)
        assert d["name"] == "filesystem"
        assert d["transport_type"] == "stdio"
        assert d["command"] == "npx"
        assert d["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]

    def test_serializes_docker_fields(self):
        from python.helpers.mcp_resource_store import McpServerResource
        from python.api.mcp_gateway_servers import resource_to_dict

        r = McpServerResource(
            name="docker-server",
            transport_type="streamable_http",
            url="http://localhost:9000/mcp",
            docker_image="ghcr.io/example/mcp-server:latest",
            docker_ports={"9000/tcp": 9000},
            created_by="admin",
        )
        d = resource_to_dict(r)
        assert d["docker_image"] == "ghcr.io/example/mcp-server:latest"
        assert d["docker_ports"] == {"9000/tcp": 9000}


# ---------------------------------------------------------------------------
# CRUD operations via handler logic
# ---------------------------------------------------------------------------


class TestListAction:
    """Test action='list' returns resources from the store."""

    def test_list_empty_store(self, store):
        from python.api.mcp_gateway_servers import handle_list

        result = handle_list(store, user_id="user1", roles=[])
        assert result["ok"] is True
        assert result["data"] == []

    def test_list_returns_accessible_resources(self, store, sample_resource):
        from python.api.mcp_gateway_servers import handle_list

        store.upsert(sample_resource)
        result = handle_list(store, user_id="user1", roles=[])
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "github"

    def test_list_filters_by_access(self, store):
        from python.helpers.mcp_resource_store import McpServerResource
        from python.api.mcp_gateway_servers import handle_list

        # Public resource (no required roles)
        store.upsert(
            McpServerResource(name="public", transport_type="stdio", created_by="admin")
        )
        # Restricted resource (requires 'engineering' role)
        store.upsert(
            McpServerResource(
                name="restricted",
                transport_type="stdio",
                created_by="admin",
                required_roles=["engineering"],
            )
        )

        # User without engineering role sees only public
        result = handle_list(store, user_id="other_user", roles=["sales"])
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "public"

    def test_list_admin_sees_all(self, store):
        from python.helpers.mcp_resource_store import McpServerResource
        from python.api.mcp_gateway_servers import handle_list

        store.upsert(
            McpServerResource(
                name="restricted",
                transport_type="stdio",
                created_by="someone",
                required_roles=["engineering"],
            )
        )

        result = handle_list(store, user_id="admin", roles=["mcp.admin"])
        assert len(result["data"]) == 1


class TestCreateAction:
    """Test action='create' adds resources to the store."""

    def test_create_http_server(self, store):
        from python.api.mcp_gateway_servers import handle_create

        result = handle_create(
            store,
            user_id="user1",
            data={
                "name": "github",
                "transport_type": "streamable_http",
                "url": "http://mcp-github:8000/mcp",
            },
        )
        assert result["ok"] is True
        assert result["data"]["name"] == "github"
        assert store.get("github") is not None

    def test_create_stdio_server(self, store):
        from python.api.mcp_gateway_servers import handle_create

        result = handle_create(
            store,
            user_id="user1",
            data={
                "name": "filesystem",
                "transport_type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            },
        )
        assert result["ok"] is True
        assert result["data"]["command"] == "npx"

    def test_create_missing_name_returns_error(self, store):
        from python.api.mcp_gateway_servers import handle_create

        result = handle_create(
            store,
            user_id="user1",
            data={"transport_type": "stdio"},
        )
        assert result.get("ok") is not True
        assert "error" in result

    def test_create_missing_transport_type_returns_error(self, store):
        from python.api.mcp_gateway_servers import handle_create

        result = handle_create(
            store,
            user_id="user1",
            data={"name": "test"},
        )
        assert result.get("ok") is not True
        assert "error" in result

    def test_create_sets_created_by(self, store):
        from python.api.mcp_gateway_servers import handle_create

        handle_create(
            store,
            user_id="user42",
            data={"name": "test", "transport_type": "stdio"},
        )
        resource = store.get("test")
        assert resource is not None
        assert resource.created_by == "user42"

    def test_create_with_docker_config(self, store):
        from python.api.mcp_gateway_servers import handle_create

        result = handle_create(
            store,
            user_id="user1",
            data={
                "name": "docker-server",
                "transport_type": "streamable_http",
                "url": "http://localhost:9000/mcp",
                "docker_image": "ghcr.io/example/mcp-server:latest",
                "docker_ports": {"9000/tcp": 9000},
            },
        )
        assert result["ok"] is True
        resource = store.get("docker-server")
        assert resource.docker_image == "ghcr.io/example/mcp-server:latest"

    def test_create_with_required_roles(self, store):
        from python.api.mcp_gateway_servers import handle_create

        result = handle_create(
            store,
            user_id="admin",
            data={
                "name": "restricted",
                "transport_type": "stdio",
                "required_roles": ["engineering"],
            },
        )
        assert result["ok"] is True
        resource = store.get("restricted")
        assert resource.required_roles == ["engineering"]


class TestUpdateAction:
    """Test action='update' modifies existing resources."""

    def test_update_existing_resource(self, store, sample_resource):
        from python.api.mcp_gateway_servers import handle_update

        store.upsert(sample_resource)
        result = handle_update(
            store,
            user_id="user1",
            roles=[],
            data={"name": "github", "url": "http://new-url:8000/mcp"},
        )
        assert result["ok"] is True
        assert result["data"]["url"] == "http://new-url:8000/mcp"

    def test_update_nonexistent_returns_error(self, store):
        from python.api.mcp_gateway_servers import handle_update

        result = handle_update(
            store,
            user_id="user1",
            roles=[],
            data={"name": "nonexistent", "url": "http://new:8000"},
        )
        assert result.get("ok") is not True
        assert "error" in result

    def test_update_requires_write_access(self, store, sample_resource):
        from python.api.mcp_gateway_servers import handle_update

        store.upsert(sample_resource)  # created_by="user1"
        result = handle_update(
            store,
            user_id="other_user",  # Not the creator
            roles=[],  # Not admin
            data={"name": "github", "url": "http://hacked:8000"},
        )
        assert result.get("ok") is not True
        assert "error" in result or "forbidden" in str(result).lower()


class TestDeleteAction:
    """Test action='delete' removes resources."""

    def test_delete_existing(self, store, sample_resource):
        from python.api.mcp_gateway_servers import handle_delete

        store.upsert(sample_resource)
        result = handle_delete(
            store,
            user_id="user1",
            roles=[],
            name="github",
        )
        assert result["ok"] is True
        assert store.get("github") is None

    def test_delete_nonexistent_returns_error(self, store):
        from python.api.mcp_gateway_servers import handle_delete

        result = handle_delete(store, user_id="user1", roles=[], name="nope")
        assert result.get("ok") is not True
        assert "error" in result

    def test_delete_requires_write_access(self, store, sample_resource):
        from python.api.mcp_gateway_servers import handle_delete

        store.upsert(sample_resource)  # created_by="user1"
        result = handle_delete(
            store,
            user_id="other_user",
            roles=[],
            name="github",
        )
        assert result.get("ok") is not True


class TestStatusAction:
    """Test action='status' returns server status."""

    def test_status_returns_container_info(self, store, sample_resource):
        from python.api.mcp_gateway_servers import handle_status

        store.upsert(sample_resource)

        # Mock container manager to avoid Docker dependency
        mock_cm = MagicMock()
        mock_cm.get_status.return_value = {
            "running": True,
            "container_id": "abc123",
            "status": "running",
        }

        result = handle_status(store, name="github", container_manager=mock_cm)
        assert result["ok"] is True
        assert result["data"]["name"] == "github"
        assert "container" in result["data"]

    def test_status_nonexistent_returns_error(self, store):
        from python.api.mcp_gateway_servers import handle_status

        result = handle_status(store, name="nonexistent")
        assert result.get("ok") is not True
        assert "error" in result
