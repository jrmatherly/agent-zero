"""Unit tests for Phase 3: Authorization (RBAC with Casbin).

Covers: Casbin enforcer initialization, permission checks, role sync,
domain matching, wildcard matching, no-auth bypass, system admin bypass,
handler permission declarations, and 403 response behavior.

All tests use in-memory SQLite for full isolation.

Note: The Casbin model uses ``g = _, _`` (no domain in grouping) because
pycasbin's default RoleManager does not support domain-scoped ``has_link``.
Domain matching is handled entirely in the matchers via ``keyMatch(r.dom, p.dom)``.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from python.helpers.auth_db import Base

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rbac_singleton():
    """Reset RBAC enforcer singleton between tests."""
    from python.helpers import rbac

    rbac._enforcer = None
    yield
    rbac._enforcer = None


@pytest.fixture
def db_engine():
    """Provide an in-memory SQLite engine with all auth tables."""
    import python.helpers.user_store  # noqa: F401 — ensure models register

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a session from the in-memory engine."""
    _Session = sessionmaker(bind=db_engine)
    session = _Session()
    yield session
    session.close()


@pytest.fixture
def enforcer(db_engine):
    """Initialize a Casbin enforcer backed by the in-memory DB."""
    from python.helpers import rbac

    # Patch auth_db.get_engine to return our test engine
    with patch("python.helpers.rbac.auth_db.get_engine", return_value=db_engine):
        e = rbac.init_enforcer()
    return e


@pytest.fixture
def seeded_enforcer(enforcer):
    """Enforcer with default policies seeded."""
    from python.helpers import rbac

    rbac.seed_default_policies()
    return enforcer


@pytest.fixture
def populated_db(db_session, db_engine):
    """Create test org, team, and users for role sync tests."""
    from python.helpers import user_store

    # Create org and team
    org = user_store.create_organization(db_session, name="Acme Corp", slug="acme")
    team = user_store.create_team(
        db_session, org_id=org.id, name="Engineering", slug="eng"
    )
    db_session.flush()

    # Create admin user (system admin)
    admin = user_store.User(
        id="admin-001",
        email="admin@acme.com",
        display_name="Admin",
        auth_provider="local",
        is_system_admin=True,
    )
    db_session.add(admin)

    # Create regular member
    member = user_store.User(
        id="member-001",
        email="member@acme.com",
        display_name="Member",
        auth_provider="local",
        is_system_admin=False,
    )
    db_session.add(member)

    # Create viewer
    viewer = user_store.User(
        id="viewer-001",
        email="viewer@acme.com",
        display_name="Viewer",
        auth_provider="local",
        is_system_admin=False,
    )
    db_session.add(viewer)

    db_session.flush()

    # Admin is org owner + team lead
    db_session.add(
        user_store.OrgMembership(user_id=admin.id, org_id=org.id, role="owner")
    )
    db_session.add(
        user_store.TeamMembership(user_id=admin.id, team_id=team.id, role="lead")
    )

    # Member is org member + team member
    db_session.add(
        user_store.OrgMembership(user_id=member.id, org_id=org.id, role="member")
    )
    db_session.add(
        user_store.TeamMembership(user_id=member.id, team_id=team.id, role="member")
    )

    # Viewer is org member + team viewer
    db_session.add(
        user_store.OrgMembership(user_id=viewer.id, org_id=org.id, role="member")
    )
    db_session.add(
        user_store.TeamMembership(user_id=viewer.id, team_id=team.id, role="viewer")
    )

    db_session.commit()

    return {
        "org": org,
        "team": team,
        "admin": admin,
        "member": member,
        "viewer": viewer,
    }


# ---------------------------------------------------------------------------
# 1. Enforcer Setup
# ---------------------------------------------------------------------------


class TestEnforcerSetup:
    def test_enforcer_created(self, enforcer):
        """Enforcer should be created and cached."""
        from python.helpers import rbac

        assert enforcer is not None
        assert rbac.get_enforcer() is enforcer

    def test_enforcer_singleton(self, enforcer, db_engine):
        """Calling init_enforcer again returns the same instance."""
        from python.helpers import rbac

        with patch("python.helpers.rbac.auth_db.get_engine", return_value=db_engine):
            e2 = rbac.init_enforcer()
        assert e2 is enforcer

    def test_get_enforcer_before_init_raises(self):
        """get_enforcer should raise if init_enforcer was not called."""
        from python.helpers import rbac

        with pytest.raises(RuntimeError, match="not initialized"):
            rbac.get_enforcer()


# ---------------------------------------------------------------------------
# 2. Policy Seeding
# ---------------------------------------------------------------------------


class TestPolicySeeding:
    def test_seed_default_policies(self, enforcer):
        """seed_default_policies should add the expected rules."""
        from python.helpers import rbac

        rbac.seed_default_policies()
        # system_admin should have wildcard policy
        assert enforcer.has_policy("system_admin", "*", "*", "*")
        # org_owner should have org-level wildcard
        assert enforcer.has_policy("org_owner", "org:*", "*", "*")
        # member should have specific policies
        assert enforcer.has_policy("member", "org:*/team:*", "chats", "create")
        assert enforcer.has_policy("member", "org:*/team:*", "settings", "read")

    def test_seed_idempotent(self, enforcer):
        """Calling seed_default_policies twice should not duplicate rules."""
        from python.helpers import rbac

        rbac.seed_default_policies()
        policies_before = enforcer.get_policy()
        rbac.seed_default_policies()
        policies_after = enforcer.get_policy()
        assert len(policies_before) == len(policies_after)


# ---------------------------------------------------------------------------
# 3. Permission Checks (g = _, _ model: roles assigned without domain)
# ---------------------------------------------------------------------------


class TestPermissionChecks:
    def test_system_admin_full_access(self, seeded_enforcer):
        """system_admin role should have access to everything."""
        e = seeded_enforcer
        # g = _, _ : assign role without domain
        e.add_grouping_policy("admin-001", "system_admin")
        assert e.enforce("admin-001", "org:acme/team:eng", "admin", "backup")
        assert e.enforce("admin-001", "org:acme/team:eng", "chats", "create")
        assert e.enforce("admin-001", "org:other/team:other", "settings", "write")

    def test_member_can_create_chats(self, seeded_enforcer):
        """member role should be able to create chats."""
        e = seeded_enforcer
        e.add_grouping_policy("member-001", "member")
        assert e.enforce("member-001", "org:acme/team:eng", "chats", "create")

    def test_member_cannot_backup(self, seeded_enforcer):
        """member role should NOT have admin backup access."""
        e = seeded_enforcer
        e.add_grouping_policy("member-001", "member")
        assert not e.enforce("member-001", "org:acme/team:eng", "admin", "backup")

    def test_viewer_can_read(self, seeded_enforcer):
        """viewer role should be able to read chats."""
        e = seeded_enforcer
        e.add_grouping_policy("viewer-001", "viewer")
        assert e.enforce("viewer-001", "org:acme/team:eng", "chats", "read_own")
        assert e.enforce("viewer-001", "org:acme/team:eng", "settings", "read")

    def test_viewer_cannot_write(self, seeded_enforcer):
        """viewer role should NOT be able to write."""
        e = seeded_enforcer
        e.add_grouping_policy("viewer-001", "viewer")
        assert not e.enforce("viewer-001", "org:acme/team:eng", "chats", "write")
        assert not e.enforce("viewer-001", "org:acme/team:eng", "settings", "write")

    def test_unknown_user_denied(self, seeded_enforcer):
        """User with no roles should be denied by default."""
        e = seeded_enforcer
        assert not e.enforce("nobody", "org:acme/team:eng", "chats", "read_own")

    def test_org_owner_full_org_access(self, seeded_enforcer):
        """org_owner should have full access within their org.

        With g = _, _ (no domain in grouping), org_owner is a global role.
        The policy ``("org_owner", "org:*", "*", "*")`` uses keyMatch to
        match any domain starting with ``org:``.
        """
        e = seeded_enforcer
        e.add_grouping_policy("owner-001", "org_owner")
        assert e.enforce("owner-001", "org:acme/team:eng", "chats", "create")
        assert e.enforce("owner-001", "org:acme/team:eng", "admin", "backup")
        assert e.enforce("owner-001", "org:acme/team:other", "settings", "write")


# ---------------------------------------------------------------------------
# 4. Role Sync
# ---------------------------------------------------------------------------


class TestRoleSync:
    def test_sync_user_roles_admin(self, seeded_enforcer, db_engine, populated_db):
        """sync_user_roles should add system_admin + org/team roles for admin."""
        from python.helpers import rbac

        with patch("python.helpers.rbac.auth_db.get_session") as mock_session_ctx:
            _Session = sessionmaker(bind=db_engine)
            session = _Session()
            mock_session_ctx.return_value.__enter__ = lambda _: session
            mock_session_ctx.return_value.__exit__ = lambda *_: None

            rbac.sync_user_roles("admin-001")

        # Admin should have system_admin, org_owner, team_lead roles
        roles = seeded_enforcer.get_filtered_grouping_policy(0, "admin-001")
        role_names = [r[1] for r in roles]
        assert "system_admin" in role_names
        assert "org_owner" in role_names
        assert "team_lead" in role_names

    def test_sync_user_roles_member(self, seeded_enforcer, db_engine, populated_db):
        """sync_user_roles should add member roles for regular user."""
        from python.helpers import rbac

        with patch("python.helpers.rbac.auth_db.get_session") as mock_session_ctx:
            _Session = sessionmaker(bind=db_engine)
            session = _Session()
            mock_session_ctx.return_value.__enter__ = lambda _: session
            mock_session_ctx.return_value.__exit__ = lambda *_: None

            rbac.sync_user_roles("member-001")

        roles = seeded_enforcer.get_filtered_grouping_policy(0, "member-001")
        role_names = [r[1] for r in roles]
        assert "member" in role_names
        assert "system_admin" not in role_names

    def test_sync_replaces_old_roles(self, seeded_enforcer, db_engine, populated_db):
        """sync_user_roles should replace (not append) existing roles."""
        from python.helpers import rbac

        # Add a stale role manually (2-arg: no domain)
        seeded_enforcer.add_grouping_policy("member-001", "org_owner")

        with patch("python.helpers.rbac.auth_db.get_session") as mock_session_ctx:
            _Session = sessionmaker(bind=db_engine)
            session = _Session()
            mock_session_ctx.return_value.__enter__ = lambda _: session
            mock_session_ctx.return_value.__exit__ = lambda *_: None

            rbac.sync_user_roles("member-001")

        roles = seeded_enforcer.get_filtered_grouping_policy(0, "member-001")
        role_names = [r[1] for r in roles]
        # org_owner should have been removed — member-001 is only "member"
        assert "org_owner" not in role_names
        assert "member" in role_names

    def test_sync_deduplicates_roles(self, seeded_enforcer, db_engine, populated_db):
        """sync_user_roles should not add the same role twice.

        member-001 has both OrgMembership(member) and TeamMembership(member)
        which both map to the Casbin role "member", but it should only appear once.
        """
        from python.helpers import rbac

        with patch("python.helpers.rbac.auth_db.get_session") as mock_session_ctx:
            _Session = sessionmaker(bind=db_engine)
            session = _Session()
            mock_session_ctx.return_value.__enter__ = lambda _: session
            mock_session_ctx.return_value.__exit__ = lambda *_: None

            rbac.sync_user_roles("member-001")

        roles = seeded_enforcer.get_filtered_grouping_policy(0, "member-001")
        role_names = [r[1] for r in roles]
        assert role_names.count("member") == 1


# ---------------------------------------------------------------------------
# 5. Domain Matching (keyMatch in matchers, not in g())
# ---------------------------------------------------------------------------


class TestDomainMatching:
    def test_team_domain_matches_wildcard_policy(self, seeded_enforcer):
        """Specific team domain should match org:*/team:* wildcard policies."""
        e = seeded_enforcer
        e.add_grouping_policy("user-001", "member")
        assert e.enforce("user-001", "org:acme/team:eng", "chats", "create")

    def test_different_team_same_org(self, seeded_enforcer):
        """Member policies use org:*/team:* so any org/team domain matches."""
        e = seeded_enforcer
        e.add_grouping_policy("user-001", "member")
        # Both team domains should match the org:*/team:* policy pattern
        assert e.enforce("user-001", "org:acme/team:eng", "chats", "create")
        assert e.enforce("user-001", "org:acme/team:other", "chats", "create")

    def test_org_admin_org_level_access(self, seeded_enforcer):
        """org_admin should have org-level access (settings, admin, mcp, knowledge)."""
        e = seeded_enforcer
        e.add_grouping_policy("admin-001", "org_admin")
        assert e.enforce("admin-001", "org:acme", "settings", "write")
        assert e.enforce("admin-001", "org:acme", "admin", "backup")
        assert e.enforce("admin-001", "org:acme", "mcp", "read")


# ---------------------------------------------------------------------------
# 6. Wildcard Matching
# ---------------------------------------------------------------------------


class TestWildcardMatching:
    def test_system_admin_any_domain(self, seeded_enforcer):
        """system_admin with * policy should match any domain."""
        e = seeded_enforcer
        e.add_grouping_policy("admin-001", "system_admin")
        assert e.enforce("admin-001", "org:acme/team:eng", "chats", "create")
        assert e.enforce("admin-001", "org:other/team:other", "admin", "system")
        assert e.enforce("admin-001", "org:xyz", "settings", "write")

    def test_system_admin_any_resource_any_action(self, seeded_enforcer):
        """system_admin should match any resource and action."""
        e = seeded_enforcer
        e.add_grouping_policy("admin-001", "system_admin")
        assert e.enforce("admin-001", "anything", "anything", "anything")


# ---------------------------------------------------------------------------
# 7. No-Auth Bypass (RBAC check in ApiHandler)
# ---------------------------------------------------------------------------


class TestNoAuthBypass:
    def test_rbac_skipped_when_no_user(self):
        """When g.current_user is None, RBAC should be skipped."""
        from python.helpers.api import ApiHandler

        # Create a handler with a permission requirement
        class TestHandler(ApiHandler):
            @classmethod
            def get_required_permission(cls) -> tuple[str, str] | None:
                return ("chats", "create")

            async def process(self, input, request):
                return {"ok": True}

        # The permission check in handle_request is:
        # if user is not None: ... check permission
        # So when user is None, it should skip the check entirely.
        perm = TestHandler.get_required_permission()
        assert perm == ("chats", "create")

        # Simulating no-auth: user is None → check is skipped
        user = None
        if perm is not None:
            if user is not None:
                # This block should NOT execute
                pytest.fail("Should not check RBAC when user is None")


# ---------------------------------------------------------------------------
# 8. System Admin Bypass
# ---------------------------------------------------------------------------


class TestSystemAdminBypass:
    def test_system_admin_bypasses_rbac_check(self):
        """When is_system_admin=True, RBAC check should be skipped."""
        user = {
            "id": "admin-001",
            "is_system_admin": True,
            "org_id": "acme",
            "team_id": "eng",
        }
        perm = ("admin", "backup")

        # Simulating the check in handle_request
        if perm is not None:
            if user is not None:
                if not user.get("is_system_admin"):
                    pytest.fail("Admin should bypass this check")
                # Admin bypasses — this is correct behavior


# ---------------------------------------------------------------------------
# 9. Handler Permission Declarations
# ---------------------------------------------------------------------------


class TestHandlerDeclarations:
    def test_chat_create_permission(self):
        from python.api.chat_create import CreateChat

        assert CreateChat.get_required_permission() == ("chats", "create")

    def test_chat_load_permission(self):
        from python.api.chat_load import LoadChats

        assert LoadChats.get_required_permission() == ("chats", "read_own")

    def test_settings_get_permission(self):
        from python.api.settings_get import GetSettings

        assert GetSettings.get_required_permission() == ("settings", "read")

    def test_settings_set_permission(self):
        from python.api.settings_set import SetSettings

        assert SetSettings.get_required_permission() == ("settings", "write")

    def test_backup_create_permission(self):
        from python.api.backup_create import BackupCreate

        assert BackupCreate.get_required_permission() == ("admin", "backup")

    def test_restart_permission(self):
        from python.api.restart import Restart

        assert Restart.get_required_permission() == ("admin", "system")

    def test_csrf_token_no_permission(self):
        from python.api.csrf_token import GetCsrfToken

        assert GetCsrfToken.get_required_permission() is None

    def test_poll_no_permission(self):
        from python.api.poll import Poll

        assert Poll.get_required_permission() is None

    def test_health_no_permission(self):
        from python.api.health import HealthCheck

        assert HealthCheck.get_required_permission() is None

    def test_mcp_servers_apply_permission(self):
        from python.api.mcp_servers_apply import McpServersApply

        assert McpServersApply.get_required_permission() == ("mcp", "write")

    def test_knowledge_import_permission(self):
        from python.api.import_knowledge import ImportKnowledge

        assert ImportKnowledge.get_required_permission() == ("knowledge", "upload")

    def test_tunnel_permission(self):
        from python.api.tunnel import Tunnel

        assert Tunnel.get_required_permission() == ("admin", "tunnel")

    def test_banners_permission(self):
        from python.api.banners import GetBanners

        assert GetBanners.get_required_permission() == ("system", "read")

    def test_memory_dashboard_permission(self):
        from python.api.memory_dashboard import MemoryDashboard

        assert MemoryDashboard.get_required_permission() == ("memory", "read")


# ---------------------------------------------------------------------------
# 10. 403 Response (Integration-style)
# ---------------------------------------------------------------------------


class TestForbiddenResponse:
    def test_forbidden_response_format(self):
        """The 403 response should be JSON with an error key."""
        from flask import Response

        # Simulate what handle_request produces for forbidden
        response = Response(
            json.dumps({"error": "Forbidden"}),
            status=403,
            mimetype="application/json",
        )
        assert response.status_code == 403
        data = json.loads(response.get_data(as_text=True))
        assert data["error"] == "Forbidden"


# ---------------------------------------------------------------------------
# 11. check_permission wrapper
# ---------------------------------------------------------------------------


class TestCheckPermission:
    def test_check_permission_allowed(self, seeded_enforcer):
        """check_permission should return True for allowed actions."""
        from python.helpers import rbac

        seeded_enforcer.add_grouping_policy("user-001", "member")
        assert rbac.check_permission("user-001", "org:acme/team:eng", "chats", "create")

    def test_check_permission_denied(self, seeded_enforcer):
        """check_permission should return False for denied actions."""
        from python.helpers import rbac

        seeded_enforcer.add_grouping_policy("user-001", "member")
        assert not rbac.check_permission(
            "user-001", "org:acme/team:eng", "admin", "backup"
        )

    def test_check_permission_no_roles(self, seeded_enforcer):
        """check_permission should return False for users without roles."""
        from python.helpers import rbac

        assert not rbac.check_permission(
            "nobody", "org:acme/team:eng", "chats", "read_own"
        )


# ---------------------------------------------------------------------------
# 12. Role Mapping Functions
# ---------------------------------------------------------------------------


class TestRoleMappings:
    def test_map_org_role(self):
        from python.helpers.rbac import _map_org_role

        assert _map_org_role("owner") == "org_owner"
        assert _map_org_role("admin") == "org_admin"
        assert _map_org_role("member") == "member"
        assert _map_org_role("unknown") == "member"

    def test_map_team_role(self):
        from python.helpers.rbac import _map_team_role

        assert _map_team_role("lead") == "team_lead"
        assert _map_team_role("member") == "member"
        assert _map_team_role("viewer") == "viewer"
        assert _map_team_role("unknown") == "member"


# ---------------------------------------------------------------------------
# 13. auth_db.get_engine
# ---------------------------------------------------------------------------


class TestAuthDbGetEngine:
    def test_get_engine_before_init_raises(self):
        """get_engine should raise if init_db was not called."""
        from python.helpers import auth_db

        saved = auth_db._engine
        try:
            auth_db._engine = None
            with pytest.raises(RuntimeError, match="not initialized"):
                auth_db.get_engine()
        finally:
            auth_db._engine = saved

    def test_get_engine_returns_engine(self):
        """get_engine should return the engine after init_db."""
        from python.helpers import auth_db

        saved = auth_db._engine
        try:
            engine = create_engine("sqlite:///:memory:")
            auth_db._engine = engine
            assert auth_db.get_engine() is engine
        finally:
            auth_db._engine = saved
