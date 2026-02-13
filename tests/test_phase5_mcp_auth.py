"""Tests for MCP server authentication (Phase 5a).

Validates configure_mcp_auth(), _get_mcp_user(), require_scopes_or_token_path(),
Bearer token fallback routing, and token-in-path coexistence.
"""

from unittest.mock import MagicMock, patch


class TestConfigureMcpAuth:
    def test_no_config_when_env_vars_missing(self, monkeypatch):
        """Without MCP_AZURE_* env vars, auth stays None."""
        monkeypatch.delenv("MCP_AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("MCP_AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MCP_AZURE_TENANT_ID", raising=False)

        from python.helpers import mcp_server

        # Reset state
        mcp_server._azure_auth_configured = False
        mcp_server.mcp_server.auth = None

        mcp_server.configure_mcp_auth()

        assert mcp_server.mcp_server.auth is None
        assert mcp_server._azure_auth_configured is False

    def test_config_with_all_env_vars(self, monkeypatch):
        """With all MCP_AZURE_* env vars, AzureProvider is assigned."""
        monkeypatch.setenv("MCP_AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("MCP_AZURE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("MCP_AZURE_TENANT_ID", "test-tenant-id")
        monkeypatch.setenv("MCP_SERVER_BASE_URL", "http://localhost:50080")

        from python.helpers import mcp_server

        # Reset state
        mcp_server._azure_auth_configured = False
        mcp_server.mcp_server.auth = None

        mcp_server.configure_mcp_auth()

        assert mcp_server.mcp_server.auth is not None
        assert mcp_server._azure_auth_configured is True

        # Clean up
        mcp_server.mcp_server.auth = None
        mcp_server._azure_auth_configured = False

    def test_partial_env_vars_skips_config(self, monkeypatch):
        """With only some MCP_AZURE_* env vars, auth stays None."""
        monkeypatch.setenv("MCP_AZURE_CLIENT_ID", "test-client-id")
        monkeypatch.delenv("MCP_AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MCP_AZURE_TENANT_ID", raising=False)

        from python.helpers import mcp_server

        mcp_server._azure_auth_configured = False
        mcp_server.mcp_server.auth = None

        mcp_server.configure_mcp_auth()

        assert mcp_server.mcp_server.auth is None
        assert mcp_server._azure_auth_configured is False


class TestParseRedirectUris:
    def test_empty_returns_none(self, monkeypatch):
        monkeypatch.delenv("MCP_AZURE_REDIRECT_URIS", raising=False)

        from python.helpers.mcp_server import _parse_redirect_uris

        assert _parse_redirect_uris() is None

    def test_single_uri(self, monkeypatch):
        monkeypatch.setenv("MCP_AZURE_REDIRECT_URIS", "http://localhost:50080/callback")

        from python.helpers.mcp_server import _parse_redirect_uris

        result = _parse_redirect_uris()
        assert result == ["http://localhost:50080/callback"]

    def test_multiple_uris(self, monkeypatch):
        monkeypatch.setenv(
            "MCP_AZURE_REDIRECT_URIS",
            "http://localhost:50080/callback, https://app.example.com/callback",
        )

        from python.helpers.mcp_server import _parse_redirect_uris

        result = _parse_redirect_uris()
        assert len(result) == 2
        assert "http://localhost:50080/callback" in result
        assert "https://app.example.com/callback" in result


class TestRequireScopesOrTokenPath:
    def test_none_token_passes(self):
        """Token-in-path mode: no Bearer token present."""
        from python.helpers.mcp_server import require_scopes_or_token_path

        check = require_scopes_or_token_path("chat")
        ctx = MagicMock()
        ctx.token = None
        assert check(ctx) is True

    def test_token_with_required_scopes_passes(self):
        from python.helpers.mcp_server import require_scopes_or_token_path

        check = require_scopes_or_token_path("chat", "tools.read")
        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.scopes = ["chat", "tools.read", "discover"]
        assert check(ctx) is True

    def test_token_missing_scope_fails(self):
        from python.helpers.mcp_server import require_scopes_or_token_path

        check = require_scopes_or_token_path("chat", "admin")
        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.scopes = ["chat"]
        assert check(ctx) is False


class TestGetMcpUser:
    async def test_returns_none_without_token(self):
        from python.helpers.mcp_server import _get_mcp_user

        with patch("python.helpers.mcp_server.get_access_token", return_value=None):
            result = await _get_mcp_user()
            assert result is None

    async def test_returns_user_from_token_claims(self):
        from python.helpers.mcp_server import _get_mcp_user

        mock_token = MagicMock()
        mock_token.claims = {
            "oid": "user-oid-123",
            "preferred_username": "test@example.com",
            "name": "Test User",
        }
        mock_token.scopes = ["chat", "tools.read"]
        mock_token.client_id = "client-456"

        with patch(
            "python.helpers.mcp_server.get_access_token", return_value=mock_token
        ):
            result = await _get_mcp_user()
            assert result is not None
            assert result["id"] == "user-oid-123"
            assert result["email"] == "test@example.com"
            assert result["name"] == "Test User"
            assert result["scopes"] == ["chat", "tools.read"]
            assert result["client_id"] == "client-456"


class TestRequireRbacMcpAccess:
    def test_none_token_passes(self):
        """Token-in-path mode passes unconditionally."""
        from python.helpers.mcp_server import require_rbac_mcp_access

        ctx = MagicMock()
        ctx.token = None
        assert require_rbac_mcp_access(ctx) is True

    def test_no_oid_claim_fails(self):
        from python.helpers.mcp_server import require_rbac_mcp_access

        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.claims = {}
        assert require_rbac_mcp_access(ctx) is False

    def test_unknown_user_fails(self):
        from python.helpers.mcp_server import require_rbac_mcp_access

        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.claims = {"oid": "unknown-user"}

        # Mock the DB lookup to return None (imports happen inside function body)
        mock_session = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx_mgr.__exit__ = MagicMock(return_value=False)

        with (
            patch("python.helpers.auth_db.get_session", return_value=mock_ctx_mgr),
            patch("python.helpers.user_store.get_user_by_id", return_value=None),
        ):
            assert require_rbac_mcp_access(ctx) is False

    def test_rbac_exception_fails_gracefully(self):
        from python.helpers.mcp_server import require_rbac_mcp_access

        ctx = MagicMock()
        ctx.token = MagicMock()
        ctx.token.claims = {"oid": "test-user"}

        with patch(
            "python.helpers.auth_db.get_session",
            side_effect=RuntimeError("DB not init"),
        ):
            # Should not raise, just return False
            result = require_rbac_mcp_access(ctx)
            assert result is False


class TestMcpRateLimiting:
    def test_within_limit_passes(self):
        from python.helpers.mcp_server import _check_mcp_rate_limit, _mcp_rate_limits

        _mcp_rate_limits.clear()
        assert _check_mcp_rate_limit("user1") is True

    def test_over_limit_fails(self):
        from python.helpers.mcp_server import (
            _MCP_RATE_LIMIT,
            _check_mcp_rate_limit,
            _mcp_rate_limits,
        )

        _mcp_rate_limits.clear()
        for _ in range(_MCP_RATE_LIMIT):
            _check_mcp_rate_limit("user2")
        assert _check_mcp_rate_limit("user2") is False

    def test_different_users_independent(self):
        from python.helpers.mcp_server import (
            _MCP_RATE_LIMIT,
            _check_mcp_rate_limit,
            _mcp_rate_limits,
        )

        _mcp_rate_limits.clear()
        for _ in range(_MCP_RATE_LIMIT):
            _check_mcp_rate_limit("user3")
        # user3 is at limit, but user4 should be fine
        assert _check_mcp_rate_limit("user4") is True


class TestDynamicMcpProxyBearerFallback:
    async def test_bearer_fallback_routes_to_http_app_when_auth_configured(self):
        """When auth is configured and path is /http without token, route to http_app."""
        from unittest.mock import AsyncMock

        from python.helpers import mcp_server as mcp_mod
        from python.helpers.mcp_server import DynamicMcpProxy

        proxy = DynamicMcpProxy.__new__(DynamicMcpProxy)
        proxy.token = "test-token-abc"
        proxy._lock = __import__("threading").RLock()

        # Create mock ASGI apps
        proxy.sse_app = AsyncMock()
        proxy.http_app = AsyncMock()

        # Simulate auth being configured
        original_auth = mcp_mod.mcp_server.auth
        mcp_mod.mcp_server.auth = MagicMock()
        try:
            # Request to /http WITHOUT a token in path — should trigger bearer fallback
            scope = {"type": "http", "path": "/http"}
            receive = AsyncMock()
            send = AsyncMock()

            await proxy(scope, receive, send)

            # http_app should have been called with rewritten path including the token
            proxy.http_app.assert_awaited_once()
            call_args = proxy.http_app.call_args
            called_scope = call_args[0][0]
            assert called_scope["path"] == f"/t-{proxy.token}/http"
        finally:
            mcp_mod.mcp_server.auth = original_auth

    async def test_no_bearer_fallback_when_auth_not_configured(self):
        """When auth is NOT configured, /http without token should raise 403."""
        from unittest.mock import AsyncMock

        from starlette.exceptions import HTTPException as StarletteHTTPException

        from python.helpers import mcp_server as mcp_mod
        from python.helpers.mcp_server import DynamicMcpProxy

        proxy = DynamicMcpProxy.__new__(DynamicMcpProxy)
        proxy.token = "test-token-xyz"
        proxy._lock = __import__("threading").RLock()
        proxy.sse_app = AsyncMock()
        proxy.http_app = AsyncMock()

        # Ensure auth is NOT configured
        original_auth = mcp_mod.mcp_server.auth
        mcp_mod.mcp_server.auth = None
        try:
            scope = {"type": "http", "path": "/http"}
            receive = AsyncMock()
            send = AsyncMock()

            import pytest

            with pytest.raises(StarletteHTTPException) as exc_info:
                await proxy(scope, receive, send)
            assert exc_info.value.status_code == 403
        finally:
            mcp_mod.mcp_server.auth = original_auth
