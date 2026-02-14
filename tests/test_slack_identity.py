# tests/test_slack_identity.py
"""Tests for Slack OAuth identity linking."""

from unittest.mock import MagicMock, patch

import pytest


class TestSlackOAuthImport:
    def test_handler_importable(self):
        from python.api.webhook_slack_oauth import WebhookSlackOauth

        assert WebhookSlackOauth is not None

    def test_requires_no_csrf(self):
        from python.api.webhook_slack_oauth import WebhookSlackOauth

        assert WebhookSlackOauth.requires_csrf() is False

    def test_get_method(self):
        from python.api.webhook_slack_oauth import WebhookSlackOauth

        assert "GET" in WebhookSlackOauth.get_methods()


class TestSlackOAuthCallback:
    @pytest.mark.asyncio
    async def test_missing_code_returns_error(self):
        from python.api.webhook_slack_oauth import WebhookSlackOauth

        handler = WebhookSlackOauth(MagicMock(), MagicMock())
        request = MagicMock()
        request.args = {}

        result = await handler.process({}, request)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_successful_oauth_links_identity(self):
        from python.api.webhook_slack_oauth import WebhookSlackOauth

        handler = WebhookSlackOauth(MagicMock(), MagicMock())
        request = MagicMock()
        request.args = {"code": "test-oauth-code"}

        mock_oauth_response = {
            "ok": True,
            "authed_user": {"id": "U_SLACK_123"},
            "team": {"id": "T_TEAM_1", "name": "Test Team"},
            "access_token": "xoxb-test-token",
        }

        with (
            patch(
                "python.api.webhook_slack_oauth._exchange_slack_code",
                return_value=mock_oauth_response,
            ),
            patch(
                "python.api.webhook_slack_oauth._link_slack_user",
            ) as mock_link,
            patch(
                "python.api.webhook_slack_oauth.session",
                {"user": {"id": "internal-user-1"}},
            ),
        ):
            result = await handler.process({}, request)

        mock_link.assert_called_once()
        assert result.get("ok") is True

    @pytest.mark.asyncio
    async def test_oauth_error_from_slack(self):
        from python.api.webhook_slack_oauth import WebhookSlackOauth

        handler = WebhookSlackOauth(MagicMock(), MagicMock())
        request = MagicMock()
        request.args = {"code": "bad-code"}

        with patch(
            "python.api.webhook_slack_oauth._exchange_slack_code",
            return_value={"ok": False, "error": "invalid_code"},
        ):
            result = await handler.process({}, request)

        assert "error" in result
