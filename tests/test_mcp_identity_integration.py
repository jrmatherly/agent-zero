"""Tests for MCP identity header injection integration."""

from python.helpers.mcp_identity import (
    build_identity_headers,
    prepare_proxy_headers,
    strip_auth_headers,
)


# ---------- Tests: build_identity_headers ----------


def test_build_identity_headers_basic():
    """build_identity_headers creates X-Mcp-* headers from user dict."""
    user = {"id": "user-123", "name": "Alice", "roles": ["admin", "dev"]}
    headers = build_identity_headers(user)
    assert headers["X-Mcp-UserId"] == "user-123"
    assert headers["X-Mcp-UserName"] == "Alice"
    assert headers["X-Mcp-Roles"] == "admin,dev"


def test_build_identity_headers_empty_user():
    """build_identity_headers handles empty user dict."""
    headers = build_identity_headers({})
    assert headers["X-Mcp-UserId"] == ""
    assert headers["X-Mcp-UserName"] == ""
    assert headers["X-Mcp-Roles"] == ""


def test_build_identity_headers_no_roles():
    """build_identity_headers handles user without roles."""
    user = {"id": "user-1", "name": "Bob"}
    headers = build_identity_headers(user)
    assert headers["X-Mcp-Roles"] == ""


# ---------- Tests: strip_auth_headers ----------


def test_strip_removes_auth_headers():
    """strip_auth_headers removes Authorization, Cookie, X-CSRF-Token."""
    headers = {
        "Authorization": "Bearer abc",
        "Cookie": "session=xyz",
        "X-CSRF-Token": "token",
        "Content-Type": "application/json",
        "Accept": "text/html",
    }
    cleaned = strip_auth_headers(headers)
    assert "Authorization" not in cleaned
    assert "Cookie" not in cleaned
    assert "X-CSRF-Token" not in cleaned
    assert cleaned["Content-Type"] == "application/json"
    assert cleaned["Accept"] == "text/html"


def test_strip_case_insensitive():
    """strip_auth_headers is case-insensitive."""
    headers = {"authorization": "Bearer abc", "COOKIE": "session=xyz"}
    cleaned = strip_auth_headers(headers)
    assert len(cleaned) == 0


def test_strip_preserves_other_headers():
    """strip_auth_headers preserves non-auth headers."""
    headers = {"X-Custom": "value", "Host": "example.com"}
    cleaned = strip_auth_headers(headers)
    assert cleaned == headers


# ---------- Tests: prepare_proxy_headers ----------


def test_prepare_proxy_headers_combined():
    """prepare_proxy_headers strips auth and injects identity."""
    original = {
        "Authorization": "Bearer secret",
        "Content-Type": "application/json",
    }
    user = {"id": "u1", "name": "Test", "roles": ["viewer"]}
    result = prepare_proxy_headers(original, user)
    assert "Authorization" not in result
    assert result["Content-Type"] == "application/json"
    assert result["X-Mcp-UserId"] == "u1"
    assert result["X-Mcp-UserName"] == "Test"
    assert result["X-Mcp-Roles"] == "viewer"
