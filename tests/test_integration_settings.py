# tests/test_integration_settings.py
"""Tests for integration settings fields."""


class TestIntegrationSettingsExist:
    def test_slack_webhook_secret_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "slack_signing_secret" in settings
        assert settings["slack_signing_secret"] == ""

    def test_slack_bot_token_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "slack_bot_token" in settings
        assert settings["slack_bot_token"] == ""

    def test_github_webhook_secret_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "github_webhook_secret" in settings
        assert settings["github_webhook_secret"] == ""

    def test_github_app_id_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "github_app_id" in settings
        assert settings["github_app_id"] == ""

    def test_jira_webhook_secret_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "jira_webhook_secret" in settings
        assert settings["jira_webhook_secret"] == ""

    def test_jira_site_url_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "jira_site_url" in settings
        assert settings["jira_site_url"] == ""

    def test_integrations_enabled_field(self):
        from python.helpers.settings import get_default_settings

        settings = get_default_settings()
        assert "integrations_enabled" in settings
        assert settings["integrations_enabled"] is False


class TestIntegrationSettingsEnvOverride:
    def test_env_override_slack(self, monkeypatch):
        monkeypatch.setenv("A0_SET_SLACK_SIGNING_SECRET", "xoxb-test")
        from python.helpers.settings import get_default_value

        val = get_default_value("slack_signing_secret", "")
        assert val == "xoxb-test"
