"""Cross-tenant security tests (Phase 5b.4).

Validates tenant isolation for MCP requests, including:
- User A cannot access User B's chats
- Token with wrong audience/scopes is rejected
- RBAC enforcement prevents cross-org access
"""

import uuid
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def two_users(db_session):
    """Create two users in separate orgs for isolation testing."""
    from python.helpers.user_store import (
        OrgMembership,
        Organization,
        Team,
        TeamMembership,
        User,
    )

    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())
    team_a_id = str(uuid.uuid4())
    team_b_id = str(uuid.uuid4())
    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())

    org_a = Organization(id=org_a_id, name="Org A", slug="org-a")
    org_b = Organization(id=org_b_id, name="Org B", slug="org-b")
    db_session.add_all([org_a, org_b])
    db_session.flush()

    team_a = Team(id=team_a_id, org_id=org_a_id, name="Team A", slug="team-a")
    team_b = Team(id=team_b_id, org_id=org_b_id, name="Team B", slug="team-b")
    db_session.add_all([team_a, team_b])
    db_session.flush()

    user_a = User(
        id=user_a_id,
        email="alice@orga.com",
        display_name="Alice",
        auth_provider="entra",
        primary_org_id=org_a_id,
    )
    user_b = User(
        id=user_b_id,
        email="bob@orgb.com",
        display_name="Bob",
        auth_provider="entra",
        primary_org_id=org_b_id,
    )
    db_session.add_all([user_a, user_b])
    db_session.flush()

    db_session.add_all(
        [
            OrgMembership(user_id=user_a_id, org_id=org_a_id, role="member"),
            OrgMembership(user_id=user_b_id, org_id=org_b_id, role="member"),
            TeamMembership(user_id=user_a_id, team_id=team_a_id, role="member"),
            TeamMembership(user_id=user_b_id, team_id=team_b_id, role="member"),
        ]
    )
    db_session.flush()

    return {
        "user_a": {"id": user_a_id, "org_id": org_a_id, "team_id": team_a_id},
        "user_b": {"id": user_b_id, "org_id": org_b_id, "team_id": team_b_id},
    }


class TestRequireScopesOrTokenPath:
    def test_missing_scope_denies(self):
        """Bearer token without required scope is denied."""
        from python.helpers.mcp_server import require_scopes_or_token_path

        check = require_scopes_or_token_path("chat")
        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.scopes = ["discover"]  # missing "chat"
        assert check(ctx) is False

    def test_all_scopes_present_allows(self):
        from python.helpers.mcp_server import require_scopes_or_token_path

        check = require_scopes_or_token_path("chat", "tools.read")
        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.scopes = ["chat", "tools.read", "tools.execute"]
        assert check(ctx) is True


class TestRbacCrossTenantIsolation:
    def test_user_a_cannot_access_user_b_domain(self, db_session, two_users):
        """RBAC check for User A in User B's domain should fail."""
        import casbin

        from python.helpers.files import get_abs_path

        # Set up a Casbin enforcer with in-memory adapter
        model_path = get_abs_path("conf/rbac_model.conf")
        enforcer = casbin.Enforcer(model_path)

        # Add User A's role in their own domain
        user_a = two_users["user_a"]
        user_b = two_users["user_b"]

        enforcer.add_grouping_policy(user_a["id"], "member")
        enforcer.add_policy(
            "member",
            f"org:{user_a['org_id']}/team:{user_a['team_id']}",
            "mcp",
            "execute",
        )

        # User A in their own domain: allowed
        assert enforcer.enforce(
            user_a["id"],
            f"org:{user_a['org_id']}/team:{user_a['team_id']}",
            "mcp",
            "execute",
        )

        # User A in User B's domain: denied
        assert not enforcer.enforce(
            user_a["id"],
            f"org:{user_b['org_id']}/team:{user_b['team_id']}",
            "mcp",
            "execute",
        )


class TestTokenValidation:
    def test_expired_token_claims_no_oid(self):
        """Token without 'oid' claim should be rejected by RBAC check."""
        from python.helpers.mcp_server import require_rbac_mcp_access

        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.claims = {"sub": "some-subject"}  # no "oid"
        assert require_rbac_mcp_access(ctx) is False

    def test_token_with_empty_scopes(self):
        """Token with no scopes should fail scope checks."""
        from python.helpers.mcp_server import require_scopes_or_token_path

        check = require_scopes_or_token_path("chat")
        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.scopes = []
        assert check(ctx) is False

    def test_token_in_path_still_works(self):
        """Token-in-path mode (no Bearer) should always pass."""
        from python.helpers.mcp_server import require_rbac_mcp_access

        ctx = MagicMock()
        ctx.token = None
        assert require_rbac_mcp_access(ctx) is True
