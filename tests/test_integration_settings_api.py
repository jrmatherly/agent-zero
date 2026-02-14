# tests/test_integration_settings_api.py
"""Tests for the integration settings API endpoint."""

from unittest.mock import MagicMock, patch

import pytest


class TestIntegrationSettingsApiImport:
    def test_handler_importable(self):
        from python.api.integration_settings_get import IntegrationSettingsGet

        assert IntegrationSettingsGet is not None

    def test_get_method_only(self):
        from python.api.integration_settings_get import IntegrationSettingsGet

        assert IntegrationSettingsGet.get_methods() == ["GET"]


class TestIntegrationSettingsApiResponse:
    @pytest.mark.asyncio
    async def test_returns_integration_settings(self):
        from python.api.integration_settings_get import IntegrationSettingsGet

        handler = IntegrationSettingsGet(MagicMock(), MagicMock())
        mock_settings = {
            "integrations_enabled": True,
            "slack_signing_secret": "xoxb-secret",
            "slack_bot_token": "xoxb-token",
            "github_webhook_secret": "gh-secret",
            "github_app_id": "12345",
            "jira_webhook_secret": "jira-secret",
            "jira_site_url": "https://myorg.atlassian.net",
        }

        with patch(
            "python.api.integration_settings_get.get_settings",
            return_value=mock_settings,
        ):
            result = await handler.process({}, MagicMock())

        assert result["integrations_enabled"] is True
        assert result["has_slack_secret"] is True
        assert result["has_slack_token"] is True
        assert result["has_github_secret"] is True
        assert result["github_app_id"] == "12345"
        assert result["has_jira_secret"] is True
        assert result["jira_site_url"] == "https://myorg.atlassian.net"

    @pytest.mark.asyncio
    async def test_masks_secrets(self):
        """Secrets should not be returned in plaintext."""
        from python.api.integration_settings_get import IntegrationSettingsGet

        handler = IntegrationSettingsGet(MagicMock(), MagicMock())
        mock_settings = {
            "integrations_enabled": False,
            "slack_signing_secret": "my-super-secret",
            "slack_bot_token": "",
            "github_webhook_secret": "",
            "github_app_id": "",
            "jira_webhook_secret": "",
            "jira_site_url": "",
        }

        with patch(
            "python.api.integration_settings_get.get_settings",
            return_value=mock_settings,
        ):
            result = await handler.process({}, MagicMock())

        # Should NOT contain the actual secret value
        assert "my-super-secret" not in str(result)
        # Should indicate whether a secret is set
        assert result["has_slack_secret"] is True
        assert result["has_slack_token"] is False

    @pytest.mark.asyncio
    async def test_empty_settings(self):
        from python.api.integration_settings_get import IntegrationSettingsGet

        handler = IntegrationSettingsGet(MagicMock(), MagicMock())
        mock_settings = {
            "integrations_enabled": False,
            "slack_signing_secret": "",
            "slack_bot_token": "",
            "github_webhook_secret": "",
            "github_app_id": "",
            "jira_webhook_secret": "",
            "jira_site_url": "",
        }

        with patch(
            "python.api.integration_settings_get.get_settings",
            return_value=mock_settings,
        ):
            result = await handler.process({}, MagicMock())

        assert result["integrations_enabled"] is False
        assert result["has_slack_secret"] is False
