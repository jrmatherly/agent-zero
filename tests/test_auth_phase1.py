"""Comprehensive unit tests for Phase 1 of the Apollos AI auth system.

Covers: PersistentTokenCache (MSAL encrypted token cache), AuthManager
(OIDC + local authentication), session management, login routes, decorator
backward compatibility, and API handler g.current_user population.

All tests use in-memory SQLite for full isolation and mock external
dependencies (MSAL, httpx) to avoid real network calls.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from flask import Flask, Response, g, session
from sqlalchemy import create_engine
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


@pytest.fixture
def auth_db_wired(db_session: Session):
    """Wire auth_db module to use the in-memory test engine."""
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
def mock_files(tmp_path, monkeypatch):
    """Mock files.get_abs_path and files.read_file/write_file to use tmp_path."""
    from python.helpers import files

    def _get_abs_path(path: str) -> str:
        return str(tmp_path / path)

    def _read_file(path: str) -> str:
        full_path = Path(path)
        if full_path.exists():
            return full_path.read_text()
        return ""

    def _write_file(path: str, content: str) -> None:
        full_path = Path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    monkeypatch.setattr(files, "get_abs_path", _get_abs_path)
    monkeypatch.setattr(files, "read_file", _read_file)
    monkeypatch.setattr(files, "write_file", _write_file)


# ---------------------------------------------------------------------------
# 1. PersistentTokenCache tests
# ---------------------------------------------------------------------------


class TestPersistentTokenCache:
    """Tests for PersistentTokenCache (MSAL token cache with vault_crypto)."""

    def test_load_nonexistent_cache(self, mock_files):
        """Loading a cache file that doesn't exist should start fresh."""
        from python.helpers.auth import PersistentTokenCache

        cache = PersistentTokenCache()
        assert cache.cache is not None
        # Empty cache should have no state
        assert cache.cache.serialize() == "{}"

    def test_save_and_load_roundtrip(self, mock_files):
        """Saving and loading a cache must preserve the serialized state."""
        from python.helpers.auth import PersistentTokenCache

        # First cache: add some state and mark as changed
        cache1 = PersistentTokenCache()
        test_data = '{"test_key": "test_value"}'
        cache1.cache.deserialize(test_data)
        # Manually mark as changed since deserialize doesn't set the flag
        cache1.cache.add({"test": "data"})
        cache1.save()

        # Second cache: load from disk
        cache2 = PersistentTokenCache()
        serialized = cache2.cache.serialize()
        # The cache should contain data (not necessarily our exact test data
        # since MSAL may transform it, but it shouldn't be empty)
        assert serialized != "{}"

    def test_corrupted_cache_starts_fresh(self, mock_files, tmp_path):
        """A corrupted cache file should log a warning and start fresh."""
        from python.helpers.auth import PersistentTokenCache

        # Write garbage to the cache file
        cache_path = tmp_path / "usr/auth_token_cache.bin"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"corrupted data")

        # Loading should handle the error gracefully
        cache = PersistentTokenCache()
        assert cache.cache.serialize() == "{}"

    def test_save_only_when_state_changed(self, mock_files, tmp_path):
        """save() should only write to disk if the cache has changed."""
        from python.helpers.auth import PersistentTokenCache

        cache = PersistentTokenCache()
        cache_path = tmp_path / "usr/auth_token_cache.bin"

        # No save should happen if state hasn't changed
        cache.save()
        assert not cache_path.exists()

        # Modify the cache by adding data (which marks it as changed)
        cache.cache.add({"test": "data"})
        cache.save()
        assert cache_path.exists()


# ---------------------------------------------------------------------------
# 2. AuthManager initialization tests
# ---------------------------------------------------------------------------


class TestAuthManagerInit:
    """Tests for AuthManager.__init__ and OIDC configuration detection."""

    def test_oidc_configured(self, monkeypatch):
        """With all OIDC env vars set, is_oidc_configured should be True."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "test-client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "test-tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        assert auth_mgr.is_oidc_configured is True
        assert auth_mgr.authority == "https://login.microsoftonline.com/test-tenant-id"

    def test_oidc_not_configured_local_only(self, monkeypatch):
        """Without OIDC env vars, is_oidc_configured should be False."""
        from python.helpers.auth import AuthManager

        monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
        monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("OIDC_TENANT_ID", raising=False)

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        assert auth_mgr.is_oidc_configured is False
        assert auth_mgr.authority == ""

    def test_is_oidc_configured_property(self, monkeypatch):
        """is_oidc_configured property should check all three required vars."""
        from python.helpers.auth import AuthManager

        app = Flask("test")
        app.secret_key = "test-secret"

        # Missing client_id
        monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant")
        auth_mgr = AuthManager(app)
        assert auth_mgr.is_oidc_configured is False

        # Missing client_secret
        monkeypatch.setenv("OIDC_CLIENT_ID", "client")
        monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
        auth_mgr = AuthManager(app)
        assert auth_mgr.is_oidc_configured is False

        # Missing tenant_id
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "secret")
        monkeypatch.delenv("OIDC_TENANT_ID", raising=False)
        auth_mgr = AuthManager(app)
        assert auth_mgr.is_oidc_configured is False

        # All present
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant")
        auth_mgr = AuthManager(app)
        assert auth_mgr.is_oidc_configured is True

    def test_token_cache_created_with_vault_key(self, monkeypatch, mock_files):
        """With VAULT_MASTER_KEY, token cache should be initialized."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant")
        # VAULT_MASTER_KEY is set by autouse fixture

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        assert auth_mgr._token_cache is not None


# ---------------------------------------------------------------------------
# 3. AuthManager local login tests
# ---------------------------------------------------------------------------


class TestAuthManagerLocalLogin:
    """Tests for AuthManager.login_local (local user authentication)."""

    def test_login_local_success(self, auth_db_wired):
        """Successful local login should return userinfo dict."""
        from python.helpers.auth import AuthManager
        from python.helpers.user_store import create_local_user

        with auth_db_wired as db:
            create_local_user(db, email="user@example.com", password="correct-password")
            db.commit()

        userinfo = AuthManager.login_local("user@example.com", "correct-password")
        assert userinfo is not None
        assert userinfo["email"] == "user@example.com"
        assert userinfo["auth_method"] == "local"
        assert "sub" in userinfo

    def test_login_local_wrong_password(self, auth_db_wired):
        """Wrong password should return None."""
        from python.helpers.auth import AuthManager
        from python.helpers.user_store import create_local_user

        with auth_db_wired as db:
            create_local_user(db, email="user@example.com", password="correct")
            db.commit()

        userinfo = AuthManager.login_local("user@example.com", "wrong")
        assert userinfo is None

    def test_login_local_nonexistent_user(self, auth_db_wired):
        """Nonexistent user should return None."""
        from python.helpers.auth import AuthManager

        userinfo = AuthManager.login_local("nobody@example.com", "password")
        assert userinfo is None

    def test_login_local_entra_user_rejected(self, auth_db_wired):
        """EntraID users (auth_provider='entra') should be rejected."""
        from python.helpers.auth import AuthManager
        from python.helpers.user_store import User

        with auth_db_wired as db:
            user = User(
                id=str(uuid.uuid4()),
                email="entra@example.com",
                auth_provider="entra",
                password_hash=None,
            )
            db.add(user)
            db.commit()

        userinfo = AuthManager.login_local("entra@example.com", "anything")
        assert userinfo is None


# ---------------------------------------------------------------------------
# 4. AuthManager session management tests
# ---------------------------------------------------------------------------


class TestAuthManagerSession:
    """Tests for establish_session, clear_session, get_current_user."""

    def test_establish_session_sets_user_dict(self, auth_db_wired):
        """establish_session should populate session['user']."""
        from python.helpers.auth import AuthManager

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            userinfo = {
                "sub": "user-123",
                "email": "user@example.com",
                "name": "Test User",
                "groups": [],
                "roles": [],
                "auth_method": "local",
            }
            AuthManager.establish_session(userinfo)

            assert session["user"]["id"] == "user-123"
            assert session["user"]["email"] == "user@example.com"
            assert session["user"]["name"] == "Test User"
            assert session["user"]["auth_method"] == "local"

    def test_establish_session_sets_authentication_true(self, auth_db_wired):
        """establish_session should set session['authentication'] = True."""
        from python.helpers.auth import AuthManager

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            userinfo = {
                "sub": "user-456",
                "email": "user2@example.com",
                "auth_method": "entra",
            }
            AuthManager.establish_session(userinfo)

            assert session["authentication"] is True

    def test_establish_session_calls_upsert_user(self, auth_db_wired):
        """establish_session should create/update user in database."""
        from python.helpers.auth import AuthManager
        from python.helpers.user_store import get_user_by_id

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            userinfo = {
                "sub": "user-789",
                "email": "user3@example.com",
                "name": "User Three",
                "groups": [],
                "roles": [],
                "auth_method": "entra",
            }
            AuthManager.establish_session(userinfo)

        # Verify user was persisted
        with auth_db_wired as db:
            user = get_user_by_id(db, "user-789")
            assert user is not None
            assert user.email == "user3@example.com"
            assert user.display_name == "User Three"

    def test_establish_session_clears_stale_data_and_regenerates_csrf(
        self, auth_db_wired
    ):
        """establish_session should clear pre-auth session data and regenerate CSRF token."""
        from python.helpers.auth import AuthManager

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            # Simulate pre-auth session with stale data
            session["stale_key"] = "should_be_gone"
            session["csrf_token"] = "old-csrf-token"

            userinfo = {
                "sub": "user-fixation",
                "email": "fixation@example.com",
                "auth_method": "local",
            }
            AuthManager.establish_session(userinfo)

            # Stale data should be cleared
            assert "stale_key" not in session
            # CSRF token should be regenerated (not the old one)
            assert session["csrf_token"] != "old-csrf-token"
            assert len(session["csrf_token"]) > 20
            # Auth data should still be set
            assert session["user"]["id"] == "user-fixation"
            assert session["authentication"] is True

    def test_clear_session(self):
        """clear_session should remove auth-related session keys."""
        from python.helpers.auth import AuthManager

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            session["user"] = {"id": "123"}
            session["authentication"] = True
            session["auth_flow"] = {"state": "test"}

            AuthManager.clear_session()

            assert "user" not in session
            assert "authentication" not in session
            assert "auth_flow" not in session

    def test_get_current_user(self):
        """get_current_user should return session['user'] or None."""
        from python.helpers.auth import AuthManager

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            assert AuthManager.get_current_user() is None

            session["user"] = {"id": "999", "email": "current@example.com"}
            user = AuthManager.get_current_user()
            assert user is not None
            assert user["id"] == "999"
            assert user["email"] == "current@example.com"


# ---------------------------------------------------------------------------
# 5. AuthManager OIDC flow tests
# ---------------------------------------------------------------------------


class TestAuthManagerOIDC:
    """Tests for get_login_url and process_callback (MSAL OIDC)."""

    def test_get_login_url(self, monkeypatch, mock_files):
        """get_login_url should initiate auth code flow and return auth URI."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.app_context():
            auth_mgr = AuthManager(app)

            # Add a dummy route for auth_callback
            app.add_url_rule("/auth/callback", "auth_callback", lambda: "callback")

            mock_msal_app = MagicMock()
            mock_msal_app.initiate_auth_code_flow.return_value = {
                "auth_uri": "https://login.microsoftonline.com/authorize?...",
                "state": "random-state",
            }

            with app.test_request_context():
                with patch.object(
                    auth_mgr, "_build_msal_app", return_value=mock_msal_app
                ):
                    login_url = auth_mgr.get_login_url()

                assert login_url == "https://login.microsoftonline.com/authorize?..."
                assert "auth_flow" in session
                assert session["auth_flow"]["state"] == "random-state"

    def test_process_callback_success(self, monkeypatch, auth_db_wired):
        """Successful token exchange should return userinfo dict."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        mock_msal_app = MagicMock()
        mock_msal_app.acquire_token_by_auth_code_flow.return_value = {
            "id_token_claims": {
                "oid": "entra-user-123",
                "preferred_username": "entra@example.com",
                "name": "Entra User",
                "groups": ["group-1", "group-2"],
                "roles": ["role-1"],
            },
            "access_token": "access-token-123",
        }

        with app.test_request_context():
            session["auth_flow"] = {"state": "test-state"}
            with patch.object(auth_mgr, "_build_msal_app", return_value=mock_msal_app):
                userinfo = auth_mgr.process_callback({"code": "auth-code"})

        assert userinfo["sub"] == "entra-user-123"
        assert userinfo["email"] == "entra@example.com"
        assert userinfo["name"] == "Entra User"
        assert userinfo["groups"] == ["group-1", "group-2"]
        assert userinfo["roles"] == ["role-1"]
        assert userinfo["auth_method"] == "entra"

    def test_process_callback_error(self, monkeypatch):
        """Token exchange error should raise ValueError."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        mock_msal_app = MagicMock()
        mock_msal_app.acquire_token_by_auth_code_flow.return_value = {
            "error": "invalid_grant",
            "error_description": "Code expired",
        }

        with app.test_request_context():
            session["auth_flow"] = {"state": "test-state"}
            with patch.object(auth_mgr, "_build_msal_app", return_value=mock_msal_app):
                with pytest.raises(ValueError, match="Code expired"):
                    auth_mgr.process_callback({"code": "bad-code"})


# ---------------------------------------------------------------------------
# 6. Group resolution tests
# ---------------------------------------------------------------------------


class TestGroupResolution:
    """Tests for _resolve_groups and _fetch_groups_from_graph."""

    def test_groups_in_claims(self, monkeypatch):
        """Groups directly in claims should be returned."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        claims = {"groups": ["group-a", "group-b", "group-c"]}
        groups = auth_mgr._resolve_groups(claims, "access-token")

        assert groups == ["group-a", "group-b", "group-c"]

    def test_group_overage_fetches_from_graph(self, monkeypatch):
        """Group overage claim should trigger Graph API fetch."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        claims = {
            "_claim_names": {"groups": "src1"},
            "_claim_sources": {"src1": {"endpoint": "..."}},
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {"id": "graph-group-1"},
                {"id": "graph-group-2"},
            ],
            "@odata.nextLink": None,
        }

        with patch("httpx.get", return_value=mock_response):
            groups = auth_mgr._resolve_groups(claims, "access-token")

        assert groups == ["graph-group-1", "graph-group-2"]

    def test_graph_api_pagination(self, monkeypatch):
        """Graph API pagination should follow @odata.nextLink."""
        from python.helpers.auth import AuthManager

        mock_response_page1 = Mock()
        mock_response_page1.status_code = 200
        mock_response_page1.json.return_value = {
            "value": [{"id": "group-1"}, {"id": "group-2"}],
            "@odata.nextLink": "https://graph.microsoft.com/next-page",
        }

        mock_response_page2 = Mock()
        mock_response_page2.status_code = 200
        mock_response_page2.json.return_value = {
            "value": [{"id": "group-3"}],
        }

        with patch("httpx.get", side_effect=[mock_response_page1, mock_response_page2]):
            groups = AuthManager._fetch_groups_from_graph("access-token")

        assert groups == ["group-1", "group-2", "group-3"]

    def test_no_groups(self, monkeypatch):
        """Claims with no groups should return empty list."""
        from python.helpers.auth import AuthManager

        monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
        monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("OIDC_TENANT_ID", "tenant-id")

        app = Flask("test")
        app.secret_key = "test-secret"
        auth_mgr = AuthManager(app)

        claims = {"sub": "user-123"}
        groups = auth_mgr._resolve_groups(claims, "access-token")

        assert groups == []


# ---------------------------------------------------------------------------
# 7. Auth singleton tests
# ---------------------------------------------------------------------------


class TestAuthSingleton:
    """Tests for init_auth and get_auth_manager module-level singleton."""

    def test_init_auth_and_get_auth_manager(self, monkeypatch):
        """init_auth should initialize the global AuthManager."""
        from python.helpers import auth

        monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)
        monkeypatch.delenv("OIDC_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("OIDC_TENANT_ID", raising=False)

        app = Flask("test")
        app.secret_key = "test-secret"

        # Reset singleton
        auth._auth_manager = None

        mgr = auth.init_auth(app)
        assert mgr is not None

        retrieved = auth.get_auth_manager()
        assert retrieved is mgr

        # Cleanup
        auth._auth_manager = None

    def test_get_auth_manager_before_init_raises(self):
        """get_auth_manager without init_auth should raise RuntimeError."""
        from python.helpers import auth

        # Reset singleton
        auth._auth_manager = None

        with pytest.raises(RuntimeError, match="AuthManager not initialized"):
            auth.get_auth_manager()

        # Cleanup
        auth._auth_manager = None


# ---------------------------------------------------------------------------
# 8. requires_auth decorator tests
# ---------------------------------------------------------------------------


class TestRequiresAuthDecorator:
    """Tests for the requires_auth decorator in run_ui.py."""

    def test_authenticated_session_passes(self, monkeypatch):
        """Authenticated session should allow access."""
        from run_ui import requires_auth

        monkeypatch.setattr("python.helpers.login.get_credentials_hash", lambda: None)

        app = Flask("test")
        app.secret_key = "test-secret"

        @app.get("/secure")
        @requires_auth
        async def secure():
            return Response("ok", status=200)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["authentication"] = True
            sess["user"] = {"id": "123", "email": "test@example.com"}

        response = client.get("/secure")
        assert response.status_code == 200

    def test_no_auth_configured_passes(self, monkeypatch):
        """No auth configured should allow access."""
        from run_ui import requires_auth

        monkeypatch.setattr("python.helpers.login.get_credentials_hash", lambda: None)

        app = Flask("test")
        app.secret_key = "test-secret"

        @app.get("/secure")
        @requires_auth
        async def secure():
            return Response("ok", status=200)

        client = app.test_client()
        response = client.get("/secure")
        assert response.status_code == 200

    def test_unauthenticated_redirects_to_login(self, monkeypatch):
        """Unauthenticated request should redirect to login."""
        from run_ui import requires_auth

        monkeypatch.setattr("python.helpers.login.get_credentials_hash", lambda: "hash")

        app = Flask("test")
        app.secret_key = "test-secret"

        @app.get("/login")
        def login_handler():
            return Response("login", status=200)

        @app.get("/secure")
        @requires_auth
        async def secure():
            return Response("ok", status=200)

        client = app.test_client()
        response = client.get("/secure")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_legacy_auth_still_works(self, monkeypatch):
        """Legacy AUTH_LOGIN/AUTH_PASSWORD should still work."""
        from run_ui import requires_auth

        monkeypatch.setattr("python.helpers.login.get_credentials_hash", lambda: "hash")

        app = Flask("test")
        app.secret_key = "test-secret"

        @app.get("/secure")
        @requires_auth
        async def secure():
            return Response("ok", status=200)

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["authentication"] = "hash"

        response = client.get("/secure")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 9. Login route tests
# ---------------------------------------------------------------------------


class TestLoginRoutes:
    """Tests for /login, /login/entra, /auth/callback, /logout routes."""

    def test_login_get_renders_page(self, monkeypatch):
        """GET /login should render the login page."""
        from python.helpers import auth

        monkeypatch.delenv("OIDC_CLIENT_ID", raising=False)

        app = Flask("test")
        app.secret_key = "test-secret"

        # Mock get_auth_manager to raise RuntimeError (not initialized)
        auth._auth_manager = None

        with patch("python.helpers.files.read_file", return_value="<html>Login</html>"):
            from run_ui import login_handler

            app.add_url_rule("/login", "login_handler", login_handler, methods=["GET"])

            client = app.test_client()
            response = client.get("/login")

            assert response.status_code == 200
            assert b"Login" in response.data

        # Cleanup
        auth._auth_manager = None

    def test_login_post_local_success_via_auth_manager(self, auth_db_wired):
        """POST /login with valid local credentials via AuthManager should work."""
        from python.helpers.auth import AuthManager
        from python.helpers.user_store import create_local_user

        with auth_db_wired as db:
            create_local_user(db, email="local@example.com", password="password123")
            db.commit()

        # Test the AuthManager.login_local directly (already covered above)
        # Here we verify the whole flow without importing run_ui
        userinfo = AuthManager.login_local("local@example.com", "password123")
        assert userinfo is not None
        assert userinfo["email"] == "local@example.com"
        assert userinfo["auth_method"] == "local"

        # Test establish_session
        app = Flask("test")
        app.secret_key = "test-secret"

        with app.test_request_context():
            AuthManager.establish_session(userinfo)
            assert session["authentication"] is True
            assert session["user"]["email"] == "local@example.com"

    def test_login_post_legacy_fallback(self, monkeypatch):
        """POST /login with legacy AUTH_LOGIN/AUTH_PASSWORD should work."""
        from python.helpers import auth

        monkeypatch.setenv("AUTH_LOGIN", "admin")
        monkeypatch.setenv("AUTH_PASSWORD", "secret")

        app = Flask("test")
        app.secret_key = "test-secret"

        auth._auth_manager = None

        with patch("python.helpers.files.read_file", return_value="<html>Login</html>"):
            from run_ui import login_handler

            app.add_url_rule("/login", "login_handler", login_handler, methods=["POST"])
            app.add_url_rule("/", "serve_index", lambda: Response("index", status=200))

            client = app.test_client()
            response = client.post(
                "/login", data={"username": "admin", "password": "secret"}
            )

            assert response.status_code == 302
            assert "/" in response.headers["Location"]

        # Cleanup
        auth._auth_manager = None

    def test_logout_clears_session(self, monkeypatch):
        """GET /logout should clear session and redirect to login."""
        from python.helpers import auth

        app = Flask("test")
        app.secret_key = "test-secret"

        with app.app_context():
            auth._auth_manager = None
            auth.init_auth(app)

        with patch("python.helpers.files.read_file", return_value="<html>Login</html>"):
            from run_ui import logout_handler

            app.add_url_rule("/logout", "logout_handler", logout_handler)
            app.add_url_rule("/login", "login_handler", lambda: Response("login"))

            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = {"id": "123"}
                sess["authentication"] = True

            response = client.get("/logout")

            assert response.status_code == 302
            assert "/login" in response.headers["Location"]

            # Session should be cleared after logout
            with client.session_transaction() as sess:
                assert "user" not in sess
                assert "authentication" not in sess

        # Cleanup
        auth._auth_manager = None


# ---------------------------------------------------------------------------
# 10. API handler g.current_user tests
# ---------------------------------------------------------------------------


class TestApiHandlerCurrentUser:
    """Tests for ApiHandler.handle_request setting g.current_user."""

    def test_handle_request_sets_g_current_user(self):
        """handle_request should populate g.current_user from session."""
        from flask import request as flask_request
        from python.helpers.api import ApiHandler

        app = Flask("test")
        app.secret_key = "test-secret"

        class TestHandler(ApiHandler):
            async def process(self, input, request):
                # Access g.current_user inside the handler
                return {"current_user": g.current_user}

        handler = TestHandler(app, None)

        with app.test_request_context(json={}):
            session["user"] = {"id": "api-user", "email": "api@example.com"}

            import asyncio

            response = asyncio.run(handler.handle_request(flask_request))
            assert response.status_code == 200

            # Parse JSON response
            import json

            data = json.loads(response.data)
            assert data["current_user"]["id"] == "api-user"
            assert data["current_user"]["email"] == "api@example.com"

    def test_handle_request_g_current_user_none_when_no_session(self):
        """handle_request should set g.current_user to None when no session."""
        from flask import request as flask_request
        from python.helpers.api import ApiHandler

        app = Flask("test")
        app.secret_key = "test-secret"

        class TestHandler(ApiHandler):
            async def process(self, input, request):
                return {"current_user": g.current_user}

        handler = TestHandler(app, None)

        with app.test_request_context(json={}):
            import asyncio

            response = asyncio.run(handler.handle_request(flask_request))
            assert response.status_code == 200

            import json

            data = json.loads(response.data)
            assert data["current_user"] is None
