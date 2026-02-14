"""Integration settings API — returns current platform integration config.

Auto-discovered at GET /integration_settings_get.

Returns integration settings with secrets masked (only boolean flags
indicating whether secrets are configured, never the actual values).
"""

from python.helpers.api import ApiHandler, Request
from python.helpers.settings import get_settings


class IntegrationSettingsGet(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    async def process(self, input: dict, request: Request) -> dict:
        settings = get_settings()

        return {
            "integrations_enabled": bool(settings.get("integrations_enabled", False)),
            "has_slack_secret": bool(settings.get("slack_signing_secret", "")),
            "has_slack_token": bool(settings.get("slack_bot_token", "")),
            "has_github_secret": bool(settings.get("github_webhook_secret", "")),
            "github_app_id": settings.get("github_app_id", ""),
            "has_jira_secret": bool(settings.get("jira_webhook_secret", "")),
            "jira_site_url": settings.get("jira_site_url", ""),
        }
