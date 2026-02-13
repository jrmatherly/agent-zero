"""Unit tests for Phase 2: User Isolation.

Covers: TenantContext (path resolution, factory methods), AgentContext
(user_id/tenant_ctx propagation, ownership filtering), persist_chat
(user-scoped serialization/deserialization), settings isolation
(tenant cascade), memory isolation (tenant-scoped paths), secrets
isolation (user-level secrets cascade), and multiuser migration.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# TenantContext Tests
# ---------------------------------------------------------------------------


class TestTenantContext:
    """Test TenantContext dataclass, factory methods, and path properties."""

    def test_system_factory(self):
        from python.helpers.tenant import SYSTEM_USER_ID, TenantContext

        ctx = TenantContext.system()
        assert ctx.user_id == SYSTEM_USER_ID
        assert ctx.is_system is True
        assert ctx.org_id == "default"
        assert ctx.team_id == "default"

    def test_from_session_user_none(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext.from_session_user(None)
        assert ctx.is_system is True

    def test_from_session_user_with_data(self):
        from python.helpers.tenant import TenantContext

        user = {"id": "user-123", "email": "test@example.com", "name": "Test"}
        ctx = TenantContext.from_session_user(user)
        assert ctx.user_id == "user-123"
        assert ctx.is_system is False
        assert ctx.org_id == "default"
        assert ctx.team_id == "default"

    def test_from_session_user_with_org_team(self):
        from python.helpers.tenant import TenantContext

        user = {"id": "u1", "org_id": "acme", "team_id": "eng"}
        ctx = TenantContext.from_session_user(user)
        assert ctx.org_id == "acme"
        assert ctx.team_id == "eng"

    def test_user_dir_path(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert ctx.user_dir == "usr/orgs/default/teams/default/members/abc"

    def test_chats_dir(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert ctx.chats_dir == "usr/orgs/default/teams/default/members/abc/chats"

    def test_memory_subdir(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert ctx.memory_subdir == "orgs/default/teams/default/members/abc/default"

    def test_settings_file(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert (
            ctx.settings_file
            == "usr/orgs/default/teams/default/members/abc/settings.json"
        )

    def test_secrets_file(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert (
            ctx.secrets_file == "usr/orgs/default/teams/default/members/abc/secrets.env"
        )

    def test_uploads_dir(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert ctx.uploads_dir == "usr/orgs/default/teams/default/members/abc/uploads"

    def test_workdir(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        assert ctx.workdir == "usr/orgs/default/teams/default/members/abc/workdir"

    def test_frozen(self):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="abc")
        with pytest.raises(AttributeError):
            ctx.user_id = "xyz"  # type: ignore[misc]

    def test_ensure_dirs(self, tmp_path):
        from python.helpers.tenant import TenantContext

        ctx = TenantContext(user_id="test-user")
        with patch(
            "python.helpers.tenant.files.get_abs_path",
            side_effect=lambda *p: str(tmp_path / "/".join(p)),
        ):
            ctx.ensure_dirs()
            assert os.path.isdir(str(tmp_path / ctx.chats_dir))
            assert os.path.isdir(str(tmp_path / ctx.uploads_dir))


# ---------------------------------------------------------------------------
# AgentContext User Filtering Tests
# ---------------------------------------------------------------------------


class TestAgentContextUserFiltering:
    """Test user_id and tenant_ctx on AgentContext."""

    @pytest.fixture(autouse=True)
    def _clean_contexts(self):
        """Clear all contexts before and after each test."""
        from agent import AgentContext

        with AgentContext._contexts_lock:
            AgentContext._contexts.clear()
        yield
        with AgentContext._contexts_lock:
            AgentContext._contexts.clear()

    @pytest.fixture
    def mock_config(self):
        from agent import AgentConfig

        return AgentConfig(
            chat_model=MagicMock(),
            utility_model=MagicMock(),
            embeddings_model=MagicMock(),
            browser_model=MagicMock(),
            mcp_servers="{}",
        )

    def test_context_stores_user_id(self, mock_config):
        from agent import AgentContext

        ctx = AgentContext(config=mock_config, user_id="user-1")
        assert ctx.user_id == "user-1"

    def test_context_stores_tenant_ctx(self, mock_config):
        from python.helpers.tenant import TenantContext

        from agent import AgentContext

        tenant = TenantContext(user_id="user-1")
        ctx = AgentContext(config=mock_config, user_id="user-1", tenant_ctx=tenant)
        assert ctx.tenant_ctx is tenant

    def test_first_for_user(self, mock_config):
        from agent import AgentContext

        ctx1 = AgentContext(config=mock_config, user_id="user-a")
        _ctx2 = AgentContext(config=mock_config, user_id="user-b")
        result = AgentContext.first_for_user("user-a")
        assert result is ctx1

    def test_first_for_user_none(self, mock_config):
        from agent import AgentContext

        _ctx = AgentContext(config=mock_config, user_id="user-a")
        assert AgentContext.first_for_user("user-z") is None

    def test_all_for_user(self, mock_config):
        from agent import AgentContext

        ctx1 = AgentContext(config=mock_config, user_id="user-a")
        _ctx2 = AgentContext(config=mock_config, user_id="user-b")
        ctx3 = AgentContext(config=mock_config, user_id="user-a")
        result = AgentContext.all_for_user("user-a")
        assert set(c.id for c in result) == {ctx1.id, ctx3.id}

    def test_output_includes_user_id(self, mock_config):
        from agent import AgentContext

        ctx = AgentContext(config=mock_config, user_id="user-1")
        out = ctx.output()
        assert out["user_id"] == "user-1"


# ---------------------------------------------------------------------------
# Persist Chat Serialization Tests
# ---------------------------------------------------------------------------


class TestPersistChatSerialization:
    """Test user_id round-trip through serialize/deserialize."""

    @pytest.fixture(autouse=True)
    def _clean_contexts(self):
        from agent import AgentContext

        with AgentContext._contexts_lock:
            AgentContext._contexts.clear()
        yield
        with AgentContext._contexts_lock:
            AgentContext._contexts.clear()

    @staticmethod
    def _stub_agent_init(self, number=0, config=None, context=None):
        """Minimal Agent.__init__ that sets required attributes without side effects."""
        self.config = config
        self.context = context
        self.number = number
        self.agent_name = f"A{number}"
        self.history = MagicMock()
        self.history.serialize.return_value = []
        self.last_user_message = None
        self.intervention = None
        self.data = {}

    def test_serialize_includes_user_id(self):
        from agent import Agent, AgentConfig, AgentContext

        from python.helpers.persist_chat import _serialize_context
        from python.helpers.tenant import TenantContext

        config = AgentConfig(
            chat_model=MagicMock(),
            utility_model=MagicMock(),
            embeddings_model=MagicMock(),
            browser_model=MagicMock(),
            mcp_servers="{}",
        )
        tenant = TenantContext(user_id="user-42")
        with patch.object(Agent, "__init__", self._stub_agent_init):
            ctx = AgentContext(config=config, user_id="user-42", tenant_ctx=tenant)
        data = _serialize_context(ctx)
        assert data["user_id"] == "user-42"

    def test_deserialize_restores_user_id(self):
        from agent import Agent, AgentConfig, AgentContext

        from python.helpers.persist_chat import (
            _deserialize_context,
            _serialize_context,
        )
        from python.helpers.tenant import TenantContext

        config = AgentConfig(
            chat_model=MagicMock(),
            utility_model=MagicMock(),
            embeddings_model=MagicMock(),
            browser_model=MagicMock(),
            mcp_servers="{}",
        )
        tenant = TenantContext(user_id="user-42")
        with patch.object(Agent, "__init__", self._stub_agent_init):
            original = AgentContext(config=config, user_id="user-42", tenant_ctx=tenant)
            data = _serialize_context(original)
            with patch(
                "python.helpers.persist_chat.initialize_agent", return_value=config
            ):
                restored = _deserialize_context(data)
        assert restored.user_id == "user-42"
        assert restored.tenant_ctx is not None
        assert restored.tenant_ctx.user_id == "user-42"


# ---------------------------------------------------------------------------
# Memory Path Isolation Tests
# ---------------------------------------------------------------------------


class TestMemoryIsolation:
    """Test tenant-scoped memory paths."""

    def test_abs_db_dir_standard(self):
        from python.helpers import memory

        path = memory.abs_db_dir("default")
        assert path.endswith("usr/memory/default")

    def test_abs_db_dir_tenant_scoped(self):
        from python.helpers import memory

        path = memory.abs_db_dir("orgs/default/teams/default/members/user-1/default")
        assert "usr/orgs/default/teams/default/members/user-1/default/memory" in path

    def test_abs_db_dir_project(self):
        from python.helpers import memory

        with patch(
            "python.helpers.memory.files.get_abs_path",
            side_effect=lambda *p: "/".join(p),
        ):
            with patch(
                "python.helpers.projects.get_project_meta_folder",
                return_value="usr/.projects/myproj",
            ):
                path = memory.abs_db_dir("projects/myproj")
                assert "memory" in path

    def test_get_context_memory_subdir_with_tenant(self):
        from agent import AgentConfig, AgentContext

        from python.helpers import memory
        from python.helpers.tenant import TenantContext

        config = AgentConfig(
            chat_model=MagicMock(),
            utility_model=MagicMock(),
            embeddings_model=MagicMock(),
            browser_model=MagicMock(),
            mcp_servers="{}",
        )
        tenant = TenantContext(user_id="user-99")
        ctx = AgentContext(config=config, user_id="user-99", tenant_ctx=tenant)

        with patch(
            "python.helpers.projects.get_context_memory_subdir", return_value=None
        ):
            subdir = memory.get_context_memory_subdir(ctx)
            assert subdir == "orgs/default/teams/default/members/user-99/default"

        # Clean up
        from agent import AgentContext as AC

        with AC._contexts_lock:
            AC._contexts.pop(ctx.id, None)


# ---------------------------------------------------------------------------
# Settings Isolation Tests
# ---------------------------------------------------------------------------


class TestSettingsIsolation:
    """Test tenant-aware settings cascade."""

    def test_get_settings_for_tenant_system(self):
        from python.helpers import settings
        from python.helpers.tenant import TenantContext

        system = TenantContext.system()
        result = settings.get_settings_for_tenant(system)
        # Should be identical to global settings
        assert result == settings.get_settings()

    def test_get_settings_for_tenant_user_no_file(self, tmp_path):
        from python.helpers import settings
        from python.helpers.tenant import TenantContext

        tenant = TenantContext(user_id="no-file-user")
        # When user settings file doesn't exist, should fall back to global
        result = settings.get_settings_for_tenant(tenant)
        global_settings = settings.get_settings()
        assert result["chat_model_provider"] == global_settings["chat_model_provider"]


# ---------------------------------------------------------------------------
# Multiuser Migration Tests
# ---------------------------------------------------------------------------


class TestMultiuserMigration:
    """Test idempotent migration logic."""

    def test_migration_skips_when_orgs_exists(self, tmp_path):
        """Migration should be a no-op when usr/orgs/ already exists."""
        from python.helpers import multiuser_migration

        # Create the orgs dir to simulate already-migrated state
        orgs_dir = tmp_path / "usr" / "orgs"
        orgs_dir.mkdir(parents=True)

        with patch(
            "python.helpers.multiuser_migration.files.get_abs_path",
            return_value=str(orgs_dir),
        ):
            # Should not raise and should return early
            multiuser_migration.migrate_to_multiuser()

    def test_migrate_global_settings(self, tmp_path):
        from python.helpers.multiuser_migration import _migrate_global_settings

        src = tmp_path / "usr" / "settings.json"
        dst = tmp_path / "usr" / "global" / "settings.json"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text('{"version": "test"}')

        with patch(
            "python.helpers.multiuser_migration.files.get_abs_path",
            side_effect=lambda p: str(tmp_path / p),
        ):
            _migrate_global_settings()
            assert dst.exists()
            assert json.loads(dst.read_text())["version"] == "test"

    def test_migrate_global_settings_idempotent(self, tmp_path):
        """Should not overwrite existing global settings."""
        from python.helpers.multiuser_migration import _migrate_global_settings

        src = tmp_path / "usr" / "settings.json"
        dst = tmp_path / "usr" / "global" / "settings.json"
        src.parent.mkdir(parents=True, exist_ok=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.write_text('{"version": "new"}')
        dst.write_text('{"version": "existing"}')

        with patch(
            "python.helpers.multiuser_migration.files.get_abs_path",
            side_effect=lambda p: str(tmp_path / p),
        ):
            _migrate_global_settings()
            # Should keep existing, not overwrite
            assert json.loads(dst.read_text())["version"] == "existing"


# ---------------------------------------------------------------------------
# Chat Path Resolution Tests
# ---------------------------------------------------------------------------


class TestChatPathResolution:
    """Test user-scoped chat path resolution."""

    def test_get_chats_folder_system(self):
        from agent import AgentConfig, AgentContext

        from python.helpers.persist_chat import _get_chats_folder
        from python.helpers.tenant import TenantContext

        config = AgentConfig(
            chat_model=MagicMock(),
            utility_model=MagicMock(),
            embeddings_model=MagicMock(),
            browser_model=MagicMock(),
            mcp_servers="{}",
        )
        system = TenantContext.system()
        ctx = AgentContext(config=config, tenant_ctx=system)
        result = _get_chats_folder(ctx)
        assert result == "usr/chats"

        # Clean up
        from agent import AgentContext as AC

        with AC._contexts_lock:
            AC._contexts.pop(ctx.id, None)

    def test_get_chats_folder_user(self):
        from agent import AgentConfig, AgentContext

        from python.helpers.persist_chat import _get_chats_folder
        from python.helpers.tenant import TenantContext

        config = AgentConfig(
            chat_model=MagicMock(),
            utility_model=MagicMock(),
            embeddings_model=MagicMock(),
            browser_model=MagicMock(),
            mcp_servers="{}",
        )
        tenant = TenantContext(user_id="user-x")
        ctx = AgentContext(config=config, user_id="user-x", tenant_ctx=tenant)
        result = _get_chats_folder(ctx)
        assert result == "usr/orgs/default/teams/default/members/user-x/chats"

        # Clean up
        from agent import AgentContext as AC

        with AC._contexts_lock:
            AC._contexts.pop(ctx.id, None)
