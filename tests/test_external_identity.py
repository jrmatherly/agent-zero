# tests/test_external_identity.py
"""Tests for external identity linking (platform user <-> internal user)."""

from unittest.mock import MagicMock


class TestExternalIdentityModel:
    def test_model_exists(self):
        from python.helpers.user_store import ExternalIdentity

        assert ExternalIdentity.__tablename__ == "external_identities"

    def test_model_fields(self):
        from python.helpers.user_store import ExternalIdentity

        columns = {c.name for c in ExternalIdentity.__table__.columns}
        assert "id" in columns
        assert "user_id" in columns
        assert "platform" in columns
        assert "external_user_id" in columns
        assert "external_display_name" in columns
        assert "access_token_vault_id" in columns
        assert "refresh_token_vault_id" in columns
        assert "token_expires_at" in columns
        assert "created_at" in columns
        assert "last_used_at" in columns

    def test_unique_constraint(self):
        """Each (platform, external_user_id) pair must be unique."""
        from python.helpers.user_store import ExternalIdentity

        constraints = ExternalIdentity.__table__.constraints
        unique_found = any(
            hasattr(c, "columns")
            and {col.name for col in c.columns} == {"platform", "external_user_id"}
            for c in constraints
        )
        assert unique_found, "Missing unique constraint on (platform, external_user_id)"


class TestExternalIdentityCRUD:
    def _get_mock_session(self):
        return MagicMock()

    def test_link_external_identity(self):
        from python.helpers.user_store import link_external_identity

        db = self._get_mock_session()
        db.query.return_value.filter.return_value.first.return_value = None

        result = link_external_identity(
            db,
            user_id="user-1",
            platform="slack",
            external_user_id="U12345",
            external_display_name="testuser",
        )
        db.add.assert_called_once()
        assert result.user_id == "user-1"
        assert result.platform == "slack"
        assert result.external_user_id == "U12345"

    def test_get_identity_by_external_id(self):
        from python.helpers.user_store import get_identity_by_external_id

        db = self._get_mock_session()
        mock_identity = MagicMock()
        mock_identity.user_id = "user-1"
        db.query.return_value.filter.return_value.first.return_value = mock_identity

        result = get_identity_by_external_id(db, "slack", "U12345")
        assert result is not None
        assert result.user_id == "user-1"

    def test_get_identity_by_external_id_not_found(self):
        from python.helpers.user_store import get_identity_by_external_id

        db = self._get_mock_session()
        db.query.return_value.filter.return_value.first.return_value = None

        result = get_identity_by_external_id(db, "slack", "UNKNOWN")
        assert result is None

    def test_list_identities_for_user(self):
        from python.helpers.user_store import list_identities_for_user

        db = self._get_mock_session()
        mock_ids = [MagicMock(), MagicMock()]
        db.query.return_value.filter.return_value.all.return_value = mock_ids

        result = list_identities_for_user(db, "user-1")
        assert len(result) == 2
