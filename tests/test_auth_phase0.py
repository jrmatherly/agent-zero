"""Comprehensive unit tests for Phase 0 of the Apollos AI auth system.

Covers: auth_db (engine/session lifecycle), vault_crypto (AES-256-GCM
encryption with HKDF derivation), user_store (ORM models + CRUD), and
auth_bootstrap (idempotent seeding of default org/team/admin).

All tests use in-memory SQLite for full isolation.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from python.helpers.auth_db import Base


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_vault_master_key(monkeypatch):
    """Set a test VAULT_MASTER_KEY and reset the cached key between tests."""
    from python.helpers import vault_crypto

    monkeypatch.setenv("VAULT_MASTER_KEY", "a" * 64)
    vault_crypto._master_key = None
    yield
    vault_crypto._master_key = None


@pytest.fixture
def db_session():
    """Provide an in-memory SQLite session with all auth tables created."""
    import python.helpers.user_store  # noqa: F401 — ensure models register on Base

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    _Session = sessionmaker(bind=engine)
    session = _Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


# ===================================================================
# 1. auth_db tests
# ===================================================================


class TestAuthDb:
    """Tests for python.helpers.auth_db (engine, session lifecycle)."""

    def test_init_db_creates_engine(self):
        """init_db() with an in-memory URL must set the module-level engine."""
        from python.helpers import auth_db

        # Save originals to restore later
        original_engine = auth_db._engine
        original_session = auth_db._SessionLocal
        try:
            auth_db._engine = None
            auth_db._SessionLocal = None

            auth_db.init_db("sqlite:///:memory:")

            assert auth_db._engine is not None
            assert auth_db._SessionLocal is not None
        finally:
            auth_db._engine = original_engine
            auth_db._SessionLocal = original_session

    def test_get_session_raises_before_init(self):
        """get_session() must raise RuntimeError when init_db() has not run."""
        from python.helpers import auth_db

        original_session = auth_db._SessionLocal
        try:
            auth_db._SessionLocal = None
            with pytest.raises(RuntimeError, match="Auth database not initialized"):
                with auth_db.get_session():
                    pass  # pragma: no cover
        finally:
            auth_db._SessionLocal = original_session

    def test_get_session_commits_on_success(self, db_session: Session):
        """Session auto-commits when the context-manager block exits cleanly."""
        from python.helpers import auth_db
        from python.helpers.user_store import Organization

        original_engine = auth_db._engine
        original_session_local = auth_db._SessionLocal

        engine = db_session.get_bind()
        _Session = sessionmaker(bind=engine)

        try:
            auth_db._engine = engine
            auth_db._SessionLocal = _Session

            with auth_db.get_session() as session:
                org = Organization(
                    id=str(uuid.uuid4()),
                    name="Commit Test Org",
                    slug="commit-test",
                )
                session.add(org)

            # Verify data persisted by opening a fresh session
            verify_session = _Session()
            result = (
                verify_session.query(Organization).filter_by(slug="commit-test").first()
            )
            assert result is not None
            assert result.name == "Commit Test Org"
            verify_session.close()
        finally:
            auth_db._engine = original_engine
            auth_db._SessionLocal = original_session_local

    def test_get_session_rolls_back_on_error(self, db_session: Session):
        """Session rolls back when an exception propagates out of the block."""
        from python.helpers import auth_db
        from python.helpers.user_store import Organization

        original_engine = auth_db._engine
        original_session_local = auth_db._SessionLocal

        engine = db_session.get_bind()
        _Session = sessionmaker(bind=engine)

        try:
            auth_db._engine = engine
            auth_db._SessionLocal = _Session

            with pytest.raises(ValueError, match="deliberate"):
                with auth_db.get_session() as session:
                    org = Organization(
                        id=str(uuid.uuid4()),
                        name="Rollback Test Org",
                        slug="rollback-test",
                    )
                    session.add(org)
                    raise ValueError("deliberate error")

            # Verify the row was NOT persisted
            verify_session = _Session()
            result = (
                verify_session.query(Organization)
                .filter_by(slug="rollback-test")
                .first()
            )
            assert result is None
            verify_session.close()
        finally:
            auth_db._engine = original_engine
            auth_db._SessionLocal = original_session_local


# ===================================================================
# 2. vault_crypto tests
# ===================================================================


class TestVaultCrypto:
    """Tests for python.helpers.vault_crypto (AES-256-GCM + HKDF)."""

    def test_encrypt_decrypt_round_trip(self):
        """encrypt() followed by decrypt() must recover the original plaintext."""
        from python.helpers.vault_crypto import decrypt, encrypt

        plaintext = "sk-supersecretapikey123"
        ct = encrypt(plaintext, purpose="api_key_vault")
        result = decrypt(ct, purpose="api_key_vault")
        assert result == plaintext

    def test_different_purpose_different_ciphertext(self):
        """Same plaintext encrypted under different purposes must differ."""
        from python.helpers.vault_crypto import encrypt

        plaintext = "same-value"
        ct_a = encrypt(plaintext, purpose="purpose_a")
        ct_b = encrypt(plaintext, purpose="purpose_b")
        # Even ignoring the random nonce, derived keys differ, so the
        # ciphertext+tag portion will differ.
        assert ct_a != ct_b

    def test_wrong_purpose_fails_decrypt(self):
        """Decrypting with a mismatched purpose must raise InvalidTag."""
        from python.helpers.vault_crypto import decrypt, encrypt

        ct = encrypt("secret", purpose="correct_purpose")
        with pytest.raises(InvalidTag):
            decrypt(ct, purpose="wrong_purpose")

    def test_nonce_uniqueness(self):
        """Two encrypt() calls with identical plaintext+purpose must produce
        different ciphertexts (random nonce ensures this)."""
        from python.helpers.vault_crypto import encrypt

        plaintext = "deterministic-input"
        ct1 = encrypt(plaintext, purpose="api_key_vault")
        ct2 = encrypt(plaintext, purpose="api_key_vault")
        assert ct1 != ct2

    def test_missing_master_key_raises(self, monkeypatch):
        """With VAULT_MASTER_KEY unset, encrypt must raise RuntimeError."""
        from python.helpers import vault_crypto
        from python.helpers.vault_crypto import encrypt

        monkeypatch.delenv("VAULT_MASTER_KEY", raising=False)
        vault_crypto._master_key = None

        with pytest.raises(RuntimeError, match="VAULT_MASTER_KEY"):
            encrypt("anything")

    def test_invalid_master_key_non_hex_raises(self, monkeypatch):
        """A VAULT_MASTER_KEY with non-hex chars must raise RuntimeError."""
        from python.helpers import vault_crypto
        from python.helpers.vault_crypto import encrypt

        monkeypatch.setenv("VAULT_MASTER_KEY", "g" * 64)  # 'g' is not hex
        vault_crypto._master_key = None

        with pytest.raises(RuntimeError, match="non-hexadecimal"):
            encrypt("anything")

    def test_invalid_master_key_wrong_length_raises(self, monkeypatch):
        """A VAULT_MASTER_KEY shorter than 64 chars must raise RuntimeError."""
        from python.helpers import vault_crypto
        from python.helpers.vault_crypto import encrypt

        monkeypatch.setenv("VAULT_MASTER_KEY", "abcd1234")  # too short
        vault_crypto._master_key = None

        with pytest.raises(RuntimeError, match="64-character hex string"):
            encrypt("anything")


# ===================================================================
# 3. user_store tests
# ===================================================================


class TestUserStoreModels:
    """Tests for ORM models and CRUD in python.helpers.user_store."""

    def test_create_organization(self, db_session: Session):
        """create_organization() must persist an org with correct fields."""
        from python.helpers.user_store import create_organization

        org = create_organization(db_session, name="Acme Corp", slug="acme")
        db_session.flush()

        assert org.id is not None
        assert org.name == "Acme Corp"
        assert org.slug == "acme"
        assert org.is_active is True
        assert org.created_at is not None

    def test_create_team(self, db_session: Session):
        """create_team() must create a team linked to its parent org."""
        from python.helpers.user_store import create_organization, create_team

        org = create_organization(db_session, name="Org With Team", slug="org-team")
        db_session.flush()

        team = create_team(db_session, org_id=org.id, name="Engineering", slug="eng")
        db_session.flush()

        assert team.id is not None
        assert team.org_id == org.id
        assert team.name == "Engineering"
        assert team.slug == "eng"
        assert team.organization.name == "Org With Team"

    def test_create_local_user(self, db_session: Session):
        """create_local_user() must hash the password with argon2."""
        from python.helpers.user_store import create_local_user

        user = create_local_user(
            db_session,
            email="dev@example.com",
            password="s3cretP@ss",
            display_name="Dev User",
        )
        db_session.flush()

        assert user.id is not None
        assert user.email == "dev@example.com"
        assert user.display_name == "Dev User"
        assert user.auth_provider == "local"
        assert user.password_hash is not None
        assert user.password_hash.startswith("$argon2")

    def test_verify_password_correct(self, db_session: Session):
        """verify_password() returns True for the correct password."""
        from python.helpers.user_store import create_local_user, verify_password

        user = create_local_user(db_session, email="ok@example.com", password="hunter2")
        db_session.flush()

        assert verify_password(user, "hunter2") is True

    def test_verify_password_wrong(self, db_session: Session):
        """verify_password() returns False for an incorrect password."""
        from python.helpers.user_store import create_local_user, verify_password

        user = create_local_user(
            db_session, email="wrong@example.com", password="correct"
        )
        db_session.flush()

        assert verify_password(user, "incorrect") is False

    def test_verify_password_no_hash(self, db_session: Session):
        """verify_password() returns False when password_hash is None."""
        from python.helpers.user_store import User, verify_password

        user = User(
            id=str(uuid.uuid4()),
            email="nohash@example.com",
            auth_provider="entra",
            password_hash=None,
        )
        db_session.add(user)
        db_session.flush()

        assert verify_password(user, "anything") is False

    def test_upsert_user_creates_new(self, db_session: Session):
        """upsert_user() creates a new User when the sub does not exist."""
        from python.helpers.user_store import get_user_by_id, upsert_user

        sub = str(uuid.uuid4())
        userinfo = {
            "sub": sub,
            "email": "new@example.com",
            "name": "New User",
        }
        user = upsert_user(db_session, userinfo)
        db_session.flush()

        assert user.id == sub
        assert user.email == "new@example.com"
        assert user.display_name == "New User"
        assert user.auth_provider == "entra"
        assert user.last_login_at is not None

        # Also retrievable via helper
        found = get_user_by_id(db_session, sub)
        assert found is not None
        assert found.email == "new@example.com"

    def test_upsert_user_updates_existing(self, db_session: Session):
        """upsert_user() updates mutable fields for an existing user."""
        from python.helpers.user_store import upsert_user

        sub = str(uuid.uuid4())
        userinfo_v1 = {
            "sub": sub,
            "email": "v1@example.com",
            "name": "Version 1",
        }
        user = upsert_user(db_session, userinfo_v1)
        db_session.flush()

        first_login = user.last_login_at

        # Update mutable fields
        userinfo_v2 = {
            "sub": sub,
            "email": "v2@example.com",
            "name": "Version 2",
        }
        updated = upsert_user(db_session, userinfo_v2)
        db_session.flush()

        assert updated.id == sub  # same row
        assert updated.email == "v2@example.com"
        assert updated.display_name == "Version 2"
        assert updated.last_login_at >= first_login

    def test_get_user_by_email(self, db_session: Session):
        """get_user_by_email() returns the correct user."""
        from python.helpers.user_store import create_local_user, get_user_by_email

        create_local_user(db_session, email="findme@example.com", password="pass")
        db_session.flush()

        found = get_user_by_email(db_session, "findme@example.com")
        assert found is not None
        assert found.email == "findme@example.com"

        missing = get_user_by_email(db_session, "nonexistent@example.com")
        assert missing is None

    def test_get_user_by_id(self, db_session: Session):
        """get_user_by_id() returns the correct user."""
        from python.helpers.user_store import create_local_user, get_user_by_id

        user = create_local_user(db_session, email="byid@example.com", password="pass")
        db_session.flush()

        found = get_user_by_id(db_session, user.id)
        assert found is not None
        assert found.email == "byid@example.com"

        missing = get_user_by_id(db_session, "nonexistent-id")
        assert missing is None

    def test_sync_group_memberships(self, db_session: Session):
        """sync_group_memberships() creates org+team memberships from mappings."""
        from python.helpers.user_store import (
            EntraGroupMapping,
            OrgMembership,
            TeamMembership,
            User,
            create_organization,
            create_team,
            sync_group_memberships,
        )

        # Setup: org, team, user, group mapping
        org = create_organization(db_session, name="Sync Org", slug="sync-org")
        db_session.flush()
        team = create_team(
            db_session, org_id=org.id, name="Sync Team", slug="sync-team"
        )
        db_session.flush()

        user = User(
            id=str(uuid.uuid4()),
            email="syncuser@example.com",
            auth_provider="entra",
        )
        db_session.add(user)
        db_session.flush()

        entra_group_id = str(uuid.uuid4())
        mapping = EntraGroupMapping(
            entra_group_id=entra_group_id,
            team_id=team.id,
            org_id=org.id,
            role="member",
        )
        db_session.add(mapping)
        db_session.flush()

        # Act
        sync_group_memberships(db_session, user, [entra_group_id])
        db_session.flush()

        # Assert org membership
        org_mem = (
            db_session.query(OrgMembership)
            .filter_by(user_id=user.id, org_id=org.id)
            .first()
        )
        assert org_mem is not None
        assert org_mem.role == "member"

        # Assert team membership
        team_mem = (
            db_session.query(TeamMembership)
            .filter_by(user_id=user.id, team_id=team.id)
            .first()
        )
        assert team_mem is not None
        assert team_mem.role == "member"

    def test_unique_constraint_org_name(self, db_session: Session):
        """Duplicate org names must raise IntegrityError."""
        from python.helpers.user_store import create_organization

        create_organization(db_session, name="Unique Org", slug="unique-org")
        db_session.flush()

        with pytest.raises(IntegrityError):
            create_organization(db_session, name="Unique Org", slug="unique-org-2")
            db_session.flush()

    def test_unique_constraint_user_email(self, db_session: Session):
        """Duplicate emails must raise IntegrityError."""
        from python.helpers.user_store import create_local_user

        create_local_user(db_session, email="dupe@example.com", password="pass1")
        db_session.flush()

        with pytest.raises(IntegrityError):
            create_local_user(db_session, email="dupe@example.com", password="pass2")
            db_session.flush()


# ===================================================================
# 4. auth_bootstrap tests
# ===================================================================


class TestAuthBootstrap:
    """Tests for python.helpers.auth_bootstrap (idempotent seeding)."""

    @pytest.fixture
    def _bootstrap_db(self, db_session: Session):
        """Wire auth_db module to use the in-memory test engine so that
        get_session() works during bootstrap, and stub out Alembic migrations.
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

    def test_bootstrap_creates_default_org_and_team(self, _bootstrap_db, monkeypatch):
        """After _seed_defaults(), the default org and team must exist."""
        from python.helpers.auth_bootstrap import _seed_defaults
        from python.helpers.user_store import Organization, Team

        # Ensure no admin env vars are set
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        _seed_defaults()

        session = _bootstrap_db
        org = session.query(Organization).filter_by(slug="default").first()
        assert org is not None
        assert org.name == "Default Org"

        team = session.query(Team).filter_by(slug="default", org_id=org.id).first()
        assert team is not None
        assert team.name == "Default Team"

    def test_bootstrap_creates_admin_when_env_vars_set(
        self, _bootstrap_db, monkeypatch
    ):
        """With ADMIN_EMAIL + ADMIN_PASSWORD, an admin user is created with
        is_system_admin=True, org owner membership, and team lead membership.
        """
        from python.helpers.auth_bootstrap import _seed_defaults
        from python.helpers.user_store import (
            OrgMembership,
            TeamMembership,
            User,
        )

        monkeypatch.setenv("ADMIN_EMAIL", "admin@test.com")
        monkeypatch.setenv("ADMIN_PASSWORD", "Str0ngP@ss!")

        _seed_defaults()

        session = _bootstrap_db
        admin = session.query(User).filter_by(email="admin@test.com").first()
        assert admin is not None
        assert admin.is_system_admin is True
        assert admin.auth_provider == "local"
        assert admin.password_hash is not None
        assert admin.password_hash.startswith("$argon2")

        # Verify org membership (owner)
        org_mem = session.query(OrgMembership).filter_by(user_id=admin.id).first()
        assert org_mem is not None
        assert org_mem.role == "owner"

        # Verify team membership (lead)
        team_mem = session.query(TeamMembership).filter_by(user_id=admin.id).first()
        assert team_mem is not None
        assert team_mem.role == "lead"

    def test_bootstrap_idempotent(self, _bootstrap_db, monkeypatch):
        """Calling _seed_defaults() twice must not create duplicate orgs."""
        from python.helpers.auth_bootstrap import _seed_defaults
        from python.helpers.user_store import Organization

        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        _seed_defaults()
        _seed_defaults()  # second call should be a no-op

        session = _bootstrap_db
        orgs = session.query(Organization).all()
        assert len(orgs) == 1

    def test_bootstrap_skips_admin_without_password(self, _bootstrap_db, monkeypatch):
        """ADMIN_EMAIL without ADMIN_PASSWORD must NOT create an admin user."""
        from python.helpers.auth_bootstrap import _seed_defaults
        from python.helpers.user_store import User

        monkeypatch.setenv("ADMIN_EMAIL", "noadmin@test.com")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        _seed_defaults()

        session = _bootstrap_db
        admin = session.query(User).filter_by(email="noadmin@test.com").first()
        assert admin is None

    def test_bootstrap_full_calls_init_and_migrate_and_seed(self, monkeypatch):
        """bootstrap() must call init_db, _run_migrations, and _seed_defaults."""
        from python.helpers import auth_bootstrap

        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        with (
            patch.object(auth_bootstrap.auth_db, "init_db") as mock_init,
            patch.object(auth_bootstrap, "_run_migrations") as mock_migrate,
            patch.object(auth_bootstrap, "_seed_defaults") as mock_seed,
        ):
            auth_bootstrap.bootstrap()

            mock_init.assert_called_once()
            mock_migrate.assert_called_once()
            mock_seed.assert_called_once()
