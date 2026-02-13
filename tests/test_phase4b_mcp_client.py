"""Comprehensive unit tests for Phase 4b MCP client infrastructure.

Covers: MCP service registry CRUD, MCP connection CRUD, VaultTokenStorage
(OAuth token persistence via encrypted vault), and the migration that creates
the ``mcp_service_registry`` and ``mcp_connections`` tables.

All tests use in-memory SQLite for full isolation.
"""

import json
import uuid

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.usefixtures("_reset_vault_master_key")


@pytest.fixture
def test_org(db_session: Session):
    """Create and return a test organization."""
    from python.helpers.user_store import create_organization

    org = create_organization(db_session, name="Test Org", slug="test-org")
    db_session.flush()
    return org


@pytest.fixture
def test_user(db_session: Session):
    """Create and return a test user."""
    from python.helpers.user_store import User

    user = User(
        id=str(uuid.uuid4()),
        email="mcpuser@example.com",
        display_name="MCP User",
        auth_provider="local",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_service(db_session: Session, test_org):
    """Create and return a test MCP service (stdio)."""
    from python.helpers.user_store import create_service

    service = create_service(
        db_session,
        name="Test stdio service",
        transport_type="stdio",
        command="node",
        args_json=json.dumps(["server.js"]),
        org_id=test_org.id,
    )
    db_session.flush()
    return service


# ===================================================================
# 1. MCP Service Registry CRUD tests
# ===================================================================


class TestMcpServiceRegistryCrud:
    """Tests for MCP service registry CRUD in python.helpers.user_store."""

    def test_create_service_stdio(self, db_session: Session, test_org):
        """create_service() with stdio transport must persist correct fields."""
        from python.helpers.user_store import create_service

        service = create_service(
            db_session,
            name="My stdio tool",
            transport_type="stdio",
            command="python",
            args_json=json.dumps(["-m", "mcp_server"]),
            env_keys_json=json.dumps(["MY_API_KEY"]),
            org_id=test_org.id,
        )
        db_session.flush()

        assert service.id is not None
        assert service.name == "My stdio tool"
        assert service.transport_type == "stdio"
        assert service.command == "python"
        assert json.loads(service.args_json) == ["-m", "mcp_server"]
        assert json.loads(service.env_keys_json) == ["MY_API_KEY"]
        assert service.org_id == test_org.id
        assert service.is_enabled is True
        assert service.created_at is not None

    def test_create_service_http(self, db_session: Session, test_org):
        """create_service() with streamable_http transport must persist correct fields."""
        from python.helpers.user_store import create_service

        service = create_service(
            db_session,
            name="Remote MCP",
            transport_type="streamable_http",
            server_url="https://mcp.example.com/v1",
            client_id="oauth-client-abc",
            default_scopes="read write",
            org_id=test_org.id,
        )
        db_session.flush()

        assert service.id is not None
        assert service.name == "Remote MCP"
        assert service.transport_type == "streamable_http"
        assert service.server_url == "https://mcp.example.com/v1"
        assert service.client_id == "oauth-client-abc"
        assert service.default_scopes == "read write"
        assert service.org_id == test_org.id

    def test_create_service_with_client_secret(self, db_session: Session, test_org):
        """create_service() with client_secret must encrypt it into client_secret_encrypted."""
        from python.helpers import vault_crypto
        from python.helpers.user_store import create_service

        service = create_service(
            db_session,
            name="Secret service",
            transport_type="streamable_http",
            server_url="https://mcp.example.com",
            client_id="client-xyz",
            client_secret="super-secret-value",
            org_id=test_org.id,
        )
        db_session.flush()

        # client_secret_encrypted should be set and not be plaintext
        assert service.client_secret_encrypted is not None
        assert service.client_secret_encrypted != "super-secret-value"

        # Decrypting should recover the original secret
        decrypted = vault_crypto.decrypt(
            service.client_secret_encrypted, purpose="mcp_service_credentials"
        )
        assert decrypted == "super-secret-value"

    def test_list_services_system_wide(self, db_session: Session):
        """list_services(org_id=None) returns only system-wide services."""
        from python.helpers.user_store import create_service, list_services

        create_service(
            db_session,
            name="System service",
            transport_type="stdio",
            command="echo",
            org_id=None,
        )
        db_session.flush()

        services = list_services(db_session, org_id=None)
        assert len(services) == 1
        assert services[0].name == "System service"
        assert services[0].org_id is None

    def test_list_services_org_scoped(self, db_session: Session, test_org):
        """list_services(org_id=X) returns org-specific AND system-wide services."""
        from python.helpers.user_store import create_service, list_services

        # Create a system-wide service
        create_service(
            db_session,
            name="System global",
            transport_type="stdio",
            command="echo",
            org_id=None,
        )
        # Create an org-scoped service
        create_service(
            db_session,
            name="Org specific",
            transport_type="stdio",
            command="node",
            org_id=test_org.id,
        )
        db_session.flush()

        services = list_services(db_session, org_id=test_org.id)
        names = {s.name for s in services}
        assert "System global" in names
        assert "Org specific" in names
        assert len(services) == 2

    def test_get_service(self, db_session: Session, test_org):
        """get_service() returns the correct service by ID."""
        from python.helpers.user_store import create_service, get_service

        service = create_service(
            db_session,
            name="Findable service",
            transport_type="stdio",
            command="cat",
            org_id=test_org.id,
        )
        db_session.flush()

        found = get_service(db_session, service.id)
        assert found is not None
        assert found.id == service.id
        assert found.name == "Findable service"

    def test_get_service_not_found(self, db_session: Session):
        """get_service() returns None for a non-existent ID."""
        from python.helpers.user_store import get_service

        result = get_service(db_session, "nonexistent-id")
        assert result is None

    def test_update_service(self, db_session: Session, test_org):
        """update_service() must update name and server_url."""
        from python.helpers.user_store import (
            create_service,
            get_service,
            update_service,
        )

        service = create_service(
            db_session,
            name="Old name",
            transport_type="streamable_http",
            server_url="https://old.example.com",
            org_id=test_org.id,
        )
        db_session.flush()

        update_service(
            db_session,
            service.id,
            name="New name",
            server_url="https://new.example.com",
        )
        db_session.flush()

        updated = get_service(db_session, service.id)
        assert updated.name == "New name"
        assert updated.server_url == "https://new.example.com"

    def test_update_service_with_client_secret(self, db_session: Session, test_org):
        """update_service() with client_secret must encrypt the new value."""
        from python.helpers import vault_crypto
        from python.helpers.user_store import (
            create_service,
            get_service,
            update_service,
        )

        service = create_service(
            db_session,
            name="Updatable",
            transport_type="streamable_http",
            server_url="https://mcp.example.com",
            client_secret="original-secret",
            org_id=test_org.id,
        )
        db_session.flush()
        original_encrypted = service.client_secret_encrypted

        update_service(db_session, service.id, client_secret="new-secret")
        db_session.flush()

        updated = get_service(db_session, service.id)
        assert updated.client_secret_encrypted != original_encrypted
        decrypted = vault_crypto.decrypt(
            updated.client_secret_encrypted, purpose="mcp_service_credentials"
        )
        assert decrypted == "new-secret"

    def test_delete_service(self, db_session: Session, test_org):
        """delete_service() must remove the service."""
        from python.helpers.user_store import (
            create_service,
            delete_service,
            get_service,
        )

        service = create_service(
            db_session,
            name="Deleteable",
            transport_type="stdio",
            command="echo",
            org_id=test_org.id,
        )
        db_session.flush()
        service_id = service.id

        delete_service(db_session, service_id)
        db_session.flush()

        assert get_service(db_session, service_id) is None

    def test_delete_service_cascades_connections(
        self, db_session: Session, test_org, test_user
    ):
        """delete_service() must also remove associated connections."""
        from python.helpers.user_store import (
            create_service,
            delete_service,
            get_connection,
            upsert_connection,
        )

        service = create_service(
            db_session,
            name="Cascade test",
            transport_type="stdio",
            command="echo",
            org_id=test_org.id,
        )
        db_session.flush()

        upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=service.id,
            scopes_granted="read",
        )
        db_session.flush()

        # Verify connection exists
        conn = get_connection(db_session, test_user.id, service.id)
        assert conn is not None

        # Delete service — should cascade to connections
        delete_service(db_session, service.id)
        db_session.flush()

        conn_after = get_connection(db_session, test_user.id, service.id)
        assert conn_after is None


# ===================================================================
# 2. MCP Connection CRUD tests
# ===================================================================


class TestMcpConnectionCrud:
    """Tests for MCP connection CRUD in python.helpers.user_store."""

    def test_upsert_connection_create(
        self, db_session: Session, test_user, test_service
    ):
        """upsert_connection() creates a new connection when none exists."""
        from python.helpers.user_store import upsert_connection

        conn = upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=test_service.id,
            scopes_granted="read write",
        )
        db_session.flush()

        assert conn.id is not None
        assert conn.user_id == test_user.id
        assert conn.service_id == test_service.id
        assert conn.scopes_granted == "read write"
        assert conn.connected_at is not None

    def test_upsert_connection_update(
        self, db_session: Session, test_user, test_service
    ):
        """upsert_connection() updates an existing connection's fields."""
        from python.helpers.user_store import upsert_connection

        conn = upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=test_service.id,
            scopes_granted="read",
        )
        db_session.flush()
        original_id = conn.id

        updated = upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=test_service.id,
            scopes_granted="read write admin",
        )
        db_session.flush()

        # Same row, updated scopes
        assert updated.id == original_id
        assert updated.scopes_granted == "read write admin"

    def test_get_connection(self, db_session: Session, test_user, test_service):
        """get_connection() returns the correct connection."""
        from python.helpers.user_store import get_connection, upsert_connection

        upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=test_service.id,
            scopes_granted="read",
        )
        db_session.flush()

        conn = get_connection(db_session, test_user.id, test_service.id)
        assert conn is not None
        assert conn.user_id == test_user.id
        assert conn.service_id == test_service.id

    def test_get_connection_not_found(self, db_session: Session):
        """get_connection() returns None for a non-existent connection."""
        from python.helpers.user_store import get_connection

        result = get_connection(db_session, "no-user", "no-service")
        assert result is None

    def test_list_connections(self, db_session: Session, test_user, test_org):
        """list_connections() returns all connections for a user."""
        from python.helpers.user_store import (
            create_service,
            list_connections,
            upsert_connection,
        )

        svc1 = create_service(
            db_session,
            name="Service A",
            transport_type="stdio",
            command="echo",
            org_id=test_org.id,
        )
        svc2 = create_service(
            db_session,
            name="Service B",
            transport_type="stdio",
            command="cat",
            org_id=test_org.id,
        )
        db_session.flush()

        upsert_connection(db_session, user_id=test_user.id, service_id=svc1.id)
        upsert_connection(db_session, user_id=test_user.id, service_id=svc2.id)
        db_session.flush()

        conns = list_connections(db_session, test_user.id)
        assert len(conns) == 2
        service_ids = {c.service_id for c in conns}
        assert svc1.id in service_ids
        assert svc2.id in service_ids

    def test_delete_connection(self, db_session: Session, test_user, test_service):
        """delete_connection() removes the connection."""
        from python.helpers.user_store import (
            delete_connection,
            get_connection,
            upsert_connection,
        )

        upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=test_service.id,
        )
        db_session.flush()

        delete_connection(db_session, test_user.id, test_service.id)
        db_session.flush()

        assert get_connection(db_session, test_user.id, test_service.id) is None

    def test_delete_connection_cleans_vault(
        self, db_session: Session, test_user, test_service
    ):
        """delete_connection() must also remove associated vault entries."""
        from python.helpers.user_store import (
            ApiKeyVault,
            delete_connection,
            store_vault_key,
            upsert_connection,
        )

        # Store vault entries for access and refresh tokens
        access_entry = store_vault_key(
            db_session,
            "mcp_token",
            f"{test_user.id}:{test_service.id}",
            "access_token",
            "test-access-token",
        )
        refresh_entry = store_vault_key(
            db_session,
            "mcp_token",
            f"{test_user.id}:{test_service.id}",
            "refresh_token",
            "test-refresh-token",
        )
        db_session.flush()

        # Create connection referencing vault entries
        upsert_connection(
            db_session,
            user_id=test_user.id,
            service_id=test_service.id,
            access_token_vault_id=access_entry.id,
            refresh_token_vault_id=refresh_entry.id,
        )
        db_session.flush()

        access_id = access_entry.id
        refresh_id = refresh_entry.id

        # Delete connection
        delete_connection(db_session, test_user.id, test_service.id)
        db_session.flush()

        # Vault entries should be gone
        assert (
            db_session.query(ApiKeyVault).filter(ApiKeyVault.id == access_id).first()
            is None
        )
        assert (
            db_session.query(ApiKeyVault).filter(ApiKeyVault.id == refresh_id).first()
            is None
        )


# ===================================================================
# 3. VaultTokenStorage tests
# ===================================================================


class TestVaultTokenStorage:
    """Tests for VaultTokenStorage in python.helpers.mcp_oauth."""

    @pytest.fixture
    def _wire_auth_db(self, db_session: Session):
        """Wire auth_db module to use the in-memory test engine so that
        get_session() works inside VaultTokenStorage methods.
        """
        from python.helpers import auth_db

        engine = db_session.get_bind()
        _Session = sessionmaker(bind=engine)

        original_engine = auth_db._engine
        original_session_local = auth_db._SessionLocal

        auth_db._engine = engine
        auth_db._SessionLocal = _Session

        yield db_session

        auth_db._engine = original_engine
        auth_db._SessionLocal = original_session_local

    @pytest.fixture
    def storage_and_ids(self, _wire_auth_db, test_user, test_service):
        """Return a VaultTokenStorage instance along with user_id and service_id."""
        from python.helpers.mcp_oauth import VaultTokenStorage

        storage = VaultTokenStorage(test_user.id, test_service.id)
        return storage, test_user.id, test_service.id

    async def test_set_and_get_tokens_roundtrip(self, storage_and_ids):
        """set_tokens() then get_tokens() must recover the access token."""
        from mcp.shared.auth import OAuthToken

        storage, user_id, service_id = storage_and_ids

        tokens = OAuthToken(
            access_token="access-abc-123",
            token_type="Bearer",
            refresh_token="refresh-xyz-789",
            expires_in=3600,
        )
        await storage.set_tokens(tokens)

        retrieved = await storage.get_tokens()
        assert retrieved is not None
        assert retrieved.access_token == "access-abc-123"
        assert retrieved.token_type == "Bearer"
        assert retrieved.refresh_token == "refresh-xyz-789"
        assert retrieved.expires_in is not None
        assert retrieved.expires_in > 0

    async def test_get_tokens_when_none(self, storage_and_ids):
        """get_tokens() returns None when no connection exists."""
        storage, _, _ = storage_and_ids

        result = await storage.get_tokens()
        assert result is None

    async def test_set_and_get_client_info(self, storage_and_ids):
        """set_client_info() then get_client_info() must recover client fields."""
        from mcp.shared.auth import OAuthClientInformationFull

        storage, _, _ = storage_and_ids

        client_info = OAuthClientInformationFull(
            client_id="my-client-id",
            client_secret="my-client-secret",
            redirect_uris=["https://app.example.com/callback"],
        )
        await storage.set_client_info(client_info)

        retrieved = await storage.get_client_info()
        assert retrieved is not None
        assert retrieved.client_id == "my-client-id"
        assert retrieved.client_secret == "my-client-secret"
        assert any(
            str(uri) == "https://app.example.com/callback"
            for uri in retrieved.redirect_uris
        )

    async def test_get_client_info_when_none(self, storage_and_ids):
        """get_client_info() returns None when no connection exists."""
        storage, _, _ = storage_and_ids

        result = await storage.get_client_info()
        assert result is None

    async def test_set_tokens_without_refresh(self, storage_and_ids):
        """set_tokens() without refresh_token stores only access_token."""
        from mcp.shared.auth import OAuthToken

        storage, _, _ = storage_and_ids

        tokens = OAuthToken(
            access_token="access-only",
            token_type="Bearer",
        )
        await storage.set_tokens(tokens)

        retrieved = await storage.get_tokens()
        assert retrieved is not None
        assert retrieved.access_token == "access-only"
        assert retrieved.refresh_token is None


# ===================================================================
# 4. Migration tests
# ===================================================================


class TestMcpMigration:
    """Tests for the MCP migration (002_mcp_service_registry)."""

    def test_migration_creates_tables(self, db_session: Session):
        """Base.metadata.create_all() must create mcp_service_registry and mcp_connections tables."""
        engine = db_session.get_bind()
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "mcp_service_registry" in tables
        assert "mcp_connections" in tables

    def test_mcp_service_registry_columns(self, db_session: Session):
        """mcp_service_registry table must have all expected columns."""
        engine = db_session.get_bind()
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("mcp_service_registry")}

        expected_columns = {
            "id",
            "org_id",
            "name",
            "transport_type",
            "command",
            "args_json",
            "env_keys_json",
            "server_url",
            "client_id",
            "client_secret_encrypted",
            "default_scopes",
            "icon_url",
            "is_enabled",
            "created_at",
        }
        assert expected_columns.issubset(columns)

    def test_mcp_connections_columns(self, db_session: Session):
        """mcp_connections table must have all expected columns."""
        engine = db_session.get_bind()
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("mcp_connections")}

        expected_columns = {
            "id",
            "user_id",
            "service_id",
            "scopes_granted",
            "access_token_vault_id",
            "refresh_token_vault_id",
            "client_info_vault_id",
            "token_expires_at",
            "connected_at",
            "last_used_at",
        }
        assert expected_columns.issubset(columns)
