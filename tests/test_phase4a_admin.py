"""Comprehensive unit tests for Phase 4a admin features.

Covers: Admin CRUD for orgs/teams/users, group mapping CRUD, vault key CRUD
with cascade resolution, and context-switch membership validation.

All tests use in-memory SQLite for full isolation.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

pytestmark = pytest.mark.usefixtures("_reset_vault_master_key")


# ===================================================================
# 1. Admin Organization CRUD
# ===================================================================


class TestAdminOrgCrud:
    """Tests for organization CRUD in python.helpers.user_store."""

    def test_create_organization(self, db_session: Session):
        """create_organization() must persist an org with correct fields."""
        from python.helpers.user_store import create_organization

        org = create_organization(db_session, name="Acme Corp", slug="acme-corp")
        db_session.flush()

        assert org.id is not None
        assert len(org.id) == 36  # UUID format
        assert org.name == "Acme Corp"
        assert org.slug == "acme-corp"
        assert org.is_active is True
        assert org.created_at is not None

    def test_list_organizations(self, db_session: Session):
        """list_organizations() returns all active orgs."""
        from python.helpers.user_store import create_organization, list_organizations

        create_organization(db_session, name="Org Alpha", slug="org-alpha")
        create_organization(db_session, name="Org Beta", slug="org-beta")
        db_session.flush()

        orgs = list_organizations(db_session)
        assert len(orgs) == 2
        names = {o.name for o in orgs}
        assert names == {"Org Alpha", "Org Beta"}

    def test_list_organizations_active_filter(self, db_session: Session):
        """list_organizations(is_active=True) excludes deactivated orgs."""
        from python.helpers.user_store import (
            create_organization,
            deactivate_organization,
            list_organizations,
        )

        org1 = create_organization(db_session, name="Active Org", slug="active-org")
        org2 = create_organization(db_session, name="Inactive Org", slug="inactive-org")
        db_session.flush()

        deactivate_organization(db_session, org2.id)
        db_session.flush()

        active = list_organizations(db_session, is_active=True)
        assert len(active) == 1
        assert active[0].id == org1.id

        inactive = list_organizations(db_session, is_active=False)
        assert len(inactive) == 1
        assert inactive[0].id == org2.id

    def test_get_organization_by_id(self, db_session: Session):
        """get_organization_by_id() returns the matching org."""
        from python.helpers.user_store import (
            create_organization,
            get_organization_by_id,
        )

        org = create_organization(db_session, name="Fetch Org", slug="fetch-org")
        db_session.flush()

        found = get_organization_by_id(db_session, org.id)
        assert found is not None
        assert found.id == org.id
        assert found.name == "Fetch Org"
        assert found.slug == "fetch-org"

    def test_get_organization_by_id_not_found(self, db_session: Session):
        """get_organization_by_id() returns None for unknown id."""
        from python.helpers.user_store import get_organization_by_id

        result = get_organization_by_id(db_session, "nonexistent-id")
        assert result is None

    def test_update_organization(self, db_session: Session):
        """update_organization() persists field changes."""
        from python.helpers.user_store import (
            create_organization,
            get_organization_by_id,
            update_organization,
        )

        org = create_organization(
            db_session, name="Original Name", slug="original-slug"
        )
        db_session.flush()

        updated = update_organization(
            db_session, org.id, name="Updated Name", slug="updated-slug"
        )
        db_session.flush()

        assert updated.name == "Updated Name"
        assert updated.slug == "updated-slug"

        # Verify persistence via fresh query
        refetched = get_organization_by_id(db_session, org.id)
        assert refetched.name == "Updated Name"

    def test_deactivate_organization(self, db_session: Session):
        """deactivate_organization() sets is_active=False."""
        from python.helpers.user_store import (
            create_organization,
            deactivate_organization,
            get_organization_by_id,
        )

        org = create_organization(
            db_session, name="Soon Inactive", slug="soon-inactive"
        )
        db_session.flush()
        assert org.is_active is True

        deactivate_organization(db_session, org.id)
        db_session.flush()

        refetched = get_organization_by_id(db_session, org.id)
        assert refetched.is_active is False


# ===================================================================
# 2. Admin Team CRUD
# ===================================================================


class TestAdminTeamCrud:
    """Tests for team CRUD in python.helpers.user_store."""

    def test_create_team(self, db_session: Session):
        """create_team() must persist a team linked to its parent org."""
        from python.helpers.user_store import create_organization, create_team

        org = create_organization(
            db_session, name="Team Parent Org", slug="team-parent"
        )
        db_session.flush()

        team = create_team(db_session, org_id=org.id, name="Engineering", slug="eng")
        db_session.flush()

        assert team.id is not None
        assert len(team.id) == 36
        assert team.org_id == org.id
        assert team.name == "Engineering"
        assert team.slug == "eng"
        assert team.created_at is not None
        assert team.organization.name == "Team Parent Org"

    def test_list_teams(self, db_session: Session):
        """list_teams() returns all teams within an organization."""
        from python.helpers.user_store import (
            create_organization,
            create_team,
            list_teams,
        )

        org = create_organization(db_session, name="Multi Team Org", slug="multi-team")
        db_session.flush()

        create_team(db_session, org_id=org.id, name="Frontend", slug="frontend")
        create_team(db_session, org_id=org.id, name="Backend", slug="backend")
        db_session.flush()

        teams = list_teams(db_session, org.id)
        assert len(teams) == 2
        names = {t.name for t in teams}
        assert names == {"Frontend", "Backend"}

    def test_get_team_by_id(self, db_session: Session):
        """get_team_by_id() returns the matching team."""
        from python.helpers.user_store import (
            create_organization,
            create_team,
            get_team_by_id,
        )

        org = create_organization(db_session, name="Get Team Org", slug="get-team-org")
        db_session.flush()
        team = create_team(db_session, org_id=org.id, name="DevOps", slug="devops")
        db_session.flush()

        found = get_team_by_id(db_session, team.id)
        assert found is not None
        assert found.id == team.id
        assert found.name == "DevOps"

    def test_update_team(self, db_session: Session):
        """update_team() persists field changes."""
        from python.helpers.user_store import (
            create_organization,
            create_team,
            get_team_by_id,
            update_team,
        )

        org = create_organization(
            db_session, name="Update Team Org", slug="update-team-org"
        )
        db_session.flush()
        team = create_team(db_session, org_id=org.id, name="Old Name", slug="old-slug")
        db_session.flush()

        updated = update_team(db_session, team.id, name="New Name", slug="new-slug")
        db_session.flush()

        assert updated.name == "New Name"
        assert updated.slug == "new-slug"
        # org_id must remain unchanged
        assert updated.org_id == org.id

        refetched = get_team_by_id(db_session, team.id)
        assert refetched.name == "New Name"

    def test_delete_team(self, db_session: Session):
        """delete_team() hard-deletes the team and its memberships."""
        from python.helpers.user_store import (
            TeamMembership,
            User,
            create_organization,
            create_team,
            delete_team,
            get_team_by_id,
        )

        org = create_organization(
            db_session, name="Delete Team Org", slug="delete-team-org"
        )
        db_session.flush()
        team = create_team(db_session, org_id=org.id, name="Doomed Team", slug="doomed")
        db_session.flush()

        # Add a user with membership to ensure cascade cleanup
        user = User(
            id=str(uuid.uuid4()),
            email="doomed@example.com",
            auth_provider="local",
        )
        db_session.add(user)
        db_session.flush()
        db_session.add(TeamMembership(user_id=user.id, team_id=team.id, role="member"))
        db_session.flush()

        delete_team(db_session, team.id)
        db_session.flush()

        assert get_team_by_id(db_session, team.id) is None
        # Membership should also be gone
        mem = db_session.query(TeamMembership).filter_by(team_id=team.id).first()
        assert mem is None


# ===================================================================
# 3. Admin User Management
# ===================================================================


class TestAdminUserManagement:
    """Tests for user management CRUD in python.helpers.user_store."""

    def test_list_users(self, db_session: Session):
        """list_users() returns all active users."""
        from python.helpers.user_store import create_local_user, list_users

        create_local_user(db_session, email="user1@example.com", password="pass1")
        create_local_user(db_session, email="user2@example.com", password="pass2")
        db_session.flush()

        users = list_users(db_session)
        assert len(users) == 2
        emails = {u.email for u in users}
        assert emails == {"user1@example.com", "user2@example.com"}

    def test_list_users_by_org(self, db_session: Session):
        """list_users(org_id=...) filters by org membership."""
        from python.helpers.user_store import (
            OrgMembership,
            create_local_user,
            create_organization,
            list_users,
        )

        org = create_organization(db_session, name="Filter Org", slug="filter-org")
        db_session.flush()

        user_in_org = create_local_user(
            db_session, email="inorg@example.com", password="pass"
        )
        create_local_user(db_session, email="outside@example.com", password="pass")
        db_session.flush()

        db_session.add(
            OrgMembership(user_id=user_in_org.id, org_id=org.id, role="member")
        )
        db_session.flush()

        filtered = list_users(db_session, org_id=org.id)
        assert len(filtered) == 1
        assert filtered[0].email == "inorg@example.com"

    def test_update_user(self, db_session: Session):
        """update_user() persists mutable field changes."""
        from python.helpers.user_store import (
            create_local_user,
            get_user_by_id,
            update_user,
        )

        user = create_local_user(
            db_session,
            email="updatable@example.com",
            password="pass",
            display_name="Old Name",
        )
        db_session.flush()

        updated = update_user(db_session, user.id, display_name="New Name")
        db_session.flush()

        assert updated.display_name == "New Name"

        refetched = get_user_by_id(db_session, user.id)
        assert refetched.display_name == "New Name"

    def test_deactivate_user(self, db_session: Session):
        """deactivate_user() sets is_active=False."""
        from python.helpers.user_store import (
            create_local_user,
            deactivate_user,
            get_user_by_id,
        )

        user = create_local_user(
            db_session, email="deactivate@example.com", password="pass"
        )
        db_session.flush()
        assert user.is_active is True

        deactivate_user(db_session, user.id)
        db_session.flush()

        refetched = get_user_by_id(db_session, user.id)
        assert refetched.is_active is False

    def test_set_user_role_org(self, db_session: Session):
        """set_user_role() creates an OrgMembership when none exists."""
        from python.helpers.user_store import (
            OrgMembership,
            create_local_user,
            create_organization,
            set_user_role,
        )

        org = create_organization(db_session, name="Role Org", slug="role-org")
        user = create_local_user(
            db_session, email="roleorg@example.com", password="pass"
        )
        db_session.flush()

        set_user_role(db_session, user_id=user.id, org_id=org.id, role="admin")
        db_session.flush()

        mem = (
            db_session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .first()
        )
        assert mem is not None
        assert mem.role == "admin"

    def test_set_user_role_team(self, db_session: Session):
        """set_user_role() creates a TeamMembership when none exists."""
        from python.helpers.user_store import (
            TeamMembership,
            create_local_user,
            create_organization,
            create_team,
            set_user_role,
        )

        org = create_organization(
            db_session, name="Team Role Org", slug="team-role-org"
        )
        db_session.flush()
        team = create_team(
            db_session, org_id=org.id, name="Team Role", slug="team-role"
        )
        user = create_local_user(
            db_session, email="roleteam@example.com", password="pass"
        )
        db_session.flush()

        set_user_role(db_session, user_id=user.id, team_id=team.id, role="lead")
        db_session.flush()

        mem = (
            db_session.query(TeamMembership)
            .filter_by(user_id=user.id, team_id=team.id)
            .first()
        )
        assert mem is not None
        assert mem.role == "lead"

    def test_set_user_role_update_existing(self, db_session: Session):
        """set_user_role() updates role on existing membership."""
        from python.helpers.user_store import (
            OrgMembership,
            create_local_user,
            create_organization,
            set_user_role,
        )

        org = create_organization(
            db_session, name="Update Role Org", slug="update-role-org"
        )
        user = create_local_user(
            db_session, email="roleupdate@example.com", password="pass"
        )
        db_session.flush()

        # Create initial membership
        set_user_role(db_session, user_id=user.id, org_id=org.id, role="member")
        db_session.flush()

        mem_before = (
            db_session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .first()
        )
        assert mem_before.role == "member"

        # Update to owner
        set_user_role(db_session, user_id=user.id, org_id=org.id, role="owner")
        db_session.flush()

        mem_after = (
            db_session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .first()
        )
        assert mem_after.role == "owner"


# ===================================================================
# 4. Group Mapping CRUD
# ===================================================================


class TestGroupMappingCrud:
    """Tests for EntraID group mapping CRUD in python.helpers.user_store."""

    def test_list_group_mappings(self, db_session: Session):
        """list_group_mappings() returns mappings for the given org."""
        from python.helpers.user_store import (
            create_organization,
            create_team,
            list_group_mappings,
            upsert_group_mapping,
        )

        org = create_organization(db_session, name="Mapping Org", slug="mapping-org")
        db_session.flush()
        team = create_team(db_session, org_id=org.id, name="Mapping Team", slug="mt")
        db_session.flush()

        gid1 = str(uuid.uuid4())
        gid2 = str(uuid.uuid4())
        upsert_group_mapping(
            db_session,
            entra_group_id=gid1,
            org_id=org.id,
            team_id=team.id,
            role="member",
        )
        upsert_group_mapping(
            db_session, entra_group_id=gid2, org_id=org.id, team_id=team.id, role="lead"
        )
        db_session.flush()

        mappings = list_group_mappings(db_session, org.id)
        assert len(mappings) == 2
        roles = {m.role for m in mappings}
        assert roles == {"member", "lead"}

    def test_upsert_group_mapping_create(self, db_session: Session):
        """upsert_group_mapping() creates a new mapping when none exists."""
        from python.helpers.user_store import (
            create_organization,
            create_team,
            upsert_group_mapping,
        )

        org = create_organization(
            db_session, name="Create Mapping Org", slug="create-mapping"
        )
        db_session.flush()
        team = create_team(db_session, org_id=org.id, name="CM Team", slug="cm")
        db_session.flush()

        gid = str(uuid.uuid4())
        mapping = upsert_group_mapping(
            db_session,
            entra_group_id=gid,
            org_id=org.id,
            team_id=team.id,
            role="member",
        )
        db_session.flush()

        assert mapping.entra_group_id == gid
        assert mapping.org_id == org.id
        assert mapping.team_id == team.id
        assert mapping.role == "member"

    def test_upsert_group_mapping_update(self, db_session: Session):
        """upsert_group_mapping() updates role on existing mapping."""
        from python.helpers.user_store import (
            EntraGroupMapping,
            create_organization,
            upsert_group_mapping,
        )

        org = create_organization(
            db_session, name="Update Mapping Org", slug="update-mapping"
        )
        db_session.flush()

        gid = str(uuid.uuid4())
        upsert_group_mapping(
            db_session, entra_group_id=gid, org_id=org.id, role="member"
        )
        db_session.flush()

        # Update the role
        updated = upsert_group_mapping(
            db_session, entra_group_id=gid, org_id=org.id, role="admin"
        )
        db_session.flush()

        assert updated.role == "admin"

        # Only one mapping should exist for this group ID
        count = (
            db_session.query(EntraGroupMapping).filter_by(entra_group_id=gid).count()
        )
        assert count == 1

    def test_delete_group_mapping(self, db_session: Session):
        """delete_group_mapping() removes the mapping."""
        from python.helpers.user_store import (
            EntraGroupMapping,
            create_organization,
            delete_group_mapping,
            upsert_group_mapping,
        )

        org = create_organization(
            db_session, name="Delete Mapping Org", slug="delete-mapping"
        )
        db_session.flush()

        gid = str(uuid.uuid4())
        upsert_group_mapping(
            db_session, entra_group_id=gid, org_id=org.id, role="member"
        )
        db_session.flush()

        delete_group_mapping(db_session, gid)
        db_session.flush()

        remaining = (
            db_session.query(EntraGroupMapping).filter_by(entra_group_id=gid).first()
        )
        assert remaining is None


# ===================================================================
# 5. Vault Key CRUD
# ===================================================================


class TestVaultKeyCrud:
    """Tests for API key vault CRUD in python.helpers.user_store."""

    def test_store_and_list_vault_keys(self, db_session: Session):
        """store_vault_key() + list_vault_keys() returns metadata only."""
        from python.helpers.user_store import list_vault_keys, store_vault_key

        user_id = str(uuid.uuid4())
        store_vault_key(
            db_session,
            owner_type="user",
            owner_id=user_id,
            key_name="API_KEY_OPENAI",
            plaintext_value="sk-test-openai-key-12345",
        )
        db_session.flush()

        keys = list_vault_keys(db_session, owner_type="user", owner_id=user_id)
        assert len(keys) == 1
        assert keys[0]["key_name"] == "API_KEY_OPENAI"
        assert keys[0]["owner_type"] == "user"
        assert keys[0]["owner_id"] == user_id
        assert keys[0]["id"] is not None
        assert keys[0]["created_at"] is not None
        # Must NOT contain the plaintext or encrypted value
        assert "encrypted_value" not in keys[0]
        assert "plaintext_value" not in keys[0]

    def test_get_vault_key_value(self, db_session: Session):
        """store_vault_key() + get_vault_key_value() round-trips plaintext."""
        from python.helpers.user_store import get_vault_key_value, store_vault_key

        user_id = str(uuid.uuid4())
        entry = store_vault_key(
            db_session,
            owner_type="user",
            owner_id=user_id,
            key_name="API_KEY_ANTHROPIC",
            plaintext_value="sk-ant-secret-value",
        )
        db_session.flush()

        decrypted = get_vault_key_value(db_session, entry.id)
        assert decrypted == "sk-ant-secret-value"

    def test_store_vault_key_upsert(self, db_session: Session):
        """Storing the same key_name twice updates the encrypted value."""
        from python.helpers.user_store import (
            ApiKeyVault,
            get_vault_key_value,
            store_vault_key,
        )

        user_id = str(uuid.uuid4())
        entry1 = store_vault_key(
            db_session,
            owner_type="user",
            owner_id=user_id,
            key_name="API_KEY_OPENAI",
            plaintext_value="sk-original-value",
        )
        db_session.flush()
        original_id = entry1.id

        entry2 = store_vault_key(
            db_session,
            owner_type="user",
            owner_id=user_id,
            key_name="API_KEY_OPENAI",
            plaintext_value="sk-updated-value",
        )
        db_session.flush()

        # Should be the same row (upsert), not a new one
        assert entry2.id == original_id

        # Only one entry should exist
        count = (
            db_session.query(ApiKeyVault)
            .filter_by(owner_type="user", owner_id=user_id, key_name="API_KEY_OPENAI")
            .count()
        )
        assert count == 1

        # Decrypted value should be the updated one
        decrypted = get_vault_key_value(db_session, entry2.id)
        assert decrypted == "sk-updated-value"

    def test_delete_vault_key(self, db_session: Session):
        """delete_vault_key() removes the entry."""
        from python.helpers.user_store import (
            delete_vault_key,
            list_vault_keys,
            store_vault_key,
        )

        user_id = str(uuid.uuid4())
        entry = store_vault_key(
            db_session,
            owner_type="user",
            owner_id=user_id,
            key_name="API_KEY_TEMP",
            plaintext_value="sk-temp-value",
        )
        db_session.flush()

        delete_vault_key(db_session, entry.id)
        db_session.flush()

        keys = list_vault_keys(db_session, owner_type="user", owner_id=user_id)
        assert len(keys) == 0

    def test_resolve_api_key_cascade(self, db_session: Session):
        """resolve_api_key() returns user-level key over team/org/system."""
        from python.helpers.user_store import resolve_api_key, store_vault_key

        user_id = str(uuid.uuid4())
        team_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        key_name = "API_KEY_OPENAI"

        # Store at all four levels
        store_vault_key(
            db_session,
            owner_type="system",
            owner_id="system",
            key_name=key_name,
            plaintext_value="sk-system-level",
        )
        store_vault_key(
            db_session,
            owner_type="org",
            owner_id=org_id,
            key_name=key_name,
            plaintext_value="sk-org-level",
        )
        store_vault_key(
            db_session,
            owner_type="team",
            owner_id=team_id,
            key_name=key_name,
            plaintext_value="sk-team-level",
        )
        store_vault_key(
            db_session,
            owner_type="user",
            owner_id=user_id,
            key_name=key_name,
            plaintext_value="sk-user-level",
        )
        db_session.flush()

        # User-level key should win
        result = resolve_api_key(db_session, key_name, user_id, team_id, org_id)
        assert result == "sk-user-level"

    def test_resolve_api_key_fallback(self, db_session: Session):
        """resolve_api_key() falls back to team when no user-level key exists."""
        from python.helpers.user_store import resolve_api_key, store_vault_key

        user_id = str(uuid.uuid4())
        team_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        key_name = "API_KEY_ANTHROPIC"

        # Store at team and org levels only (no user-level)
        store_vault_key(
            db_session,
            owner_type="org",
            owner_id=org_id,
            key_name=key_name,
            plaintext_value="sk-org-anthropic",
        )
        store_vault_key(
            db_session,
            owner_type="team",
            owner_id=team_id,
            key_name=key_name,
            plaintext_value="sk-team-anthropic",
        )
        db_session.flush()

        # Team-level key should be returned (user has none, team is next)
        result = resolve_api_key(db_session, key_name, user_id, team_id, org_id)
        assert result == "sk-team-anthropic"


# ===================================================================
# 6. Context Switch Validation
# ===================================================================


class TestContextSwitchValidation:
    """Tests for context switch membership validation logic.

    These test the underlying DB queries that SwitchContext API uses,
    without requiring Flask request context.
    """

    def test_switch_with_valid_membership(self, db_session: Session):
        """User with org + team membership can switch context (query succeeds)."""
        from python.helpers.user_store import (
            OrgMembership,
            TeamMembership,
            create_local_user,
            create_organization,
            create_team,
        )

        org = create_organization(db_session, name="Switch Org", slug="switch-org")
        db_session.flush()
        team = create_team(
            db_session, org_id=org.id, name="Switch Team", slug="sw-team"
        )
        user = create_local_user(
            db_session, email="switcher@example.com", password="pass"
        )
        db_session.flush()

        db_session.add(OrgMembership(user_id=user.id, org_id=org.id, role="member"))
        db_session.add(TeamMembership(user_id=user.id, team_id=team.id, role="member"))
        db_session.flush()

        # Simulate the validation queries from SwitchContext
        om = (
            db_session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .first()
        )
        assert om is not None
        assert om.role == "member"

        tm = (
            db_session.query(TeamMembership)
            .filter_by(user_id=user.id, team_id=team.id)
            .first()
        )
        assert tm is not None
        assert tm.role == "member"

    def test_switch_without_membership_denied(self, db_session: Session):
        """User without org/team membership gets no result (would be 403)."""
        from python.helpers.user_store import (
            OrgMembership,
            TeamMembership,
            create_local_user,
            create_organization,
            create_team,
        )

        org = create_organization(db_session, name="Denied Org", slug="denied-org")
        db_session.flush()
        team = create_team(
            db_session, org_id=org.id, name="Denied Team", slug="denied-team"
        )
        user = create_local_user(
            db_session, email="denied@example.com", password="pass"
        )
        db_session.flush()

        # User has NO memberships — simulate the SwitchContext validation
        om = (
            db_session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .first()
        )
        assert om is None  # would result in 403

        tm = (
            db_session.query(TeamMembership)
            .filter_by(user_id=user.id, team_id=team.id)
            .first()
        )
        assert tm is None  # would result in 403
