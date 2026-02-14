"""Slack OAuth callback handler — links Slack users to internal accounts.

Auto-discovered at GET /webhook_slack_oauth.

OAuth2 flow:
1. User clicks "Connect Slack" in the UI
2. Redirected to Slack OAuth consent
3. Slack redirects back here with a code
4. We exchange the code for tokens and link the identity
"""

import httpx

from python.helpers.api import ApiHandler, Request, Response, session
from python.helpers.print_style import PrintStyle


def _get_slack_credentials() -> tuple[str, str]:
    """Retrieve Slack OAuth credentials from settings."""
    from python.helpers.settings import get_settings

    settings = get_settings()
    client_id = settings.get("slack_app_id", "")
    client_secret = settings.get("slack_signing_secret", "")
    return client_id, client_secret


def _exchange_slack_code(code: str) -> dict:
    """Exchange an OAuth code for Slack access tokens."""
    client_id, client_secret = _get_slack_credentials()
    resp = httpx.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
    )
    return resp.json()


def _link_slack_user(
    internal_user_id: str,
    slack_user_id: str,
    team_id: str,
    access_token: str,
) -> None:
    """Link a Slack user to an internal user account."""
    from python.helpers.auth_db import get_session
    from python.helpers.user_store import link_external_identity

    with get_session() as db:
        link_external_identity(
            db,
            user_id=internal_user_id,
            platform="slack",
            external_user_id=slack_user_id,
            external_display_name=None,
            external_team_id=team_id,
        )
        db.commit()

    PrintStyle(font_color="cyan", padding=False).print(
        f"Linked Slack user {slack_user_id} to internal user {internal_user_id}"
    )


class WebhookSlackOauth(ApiHandler):
    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        code = request.args.get("code")
        if not code:
            return {"error": "Missing OAuth code parameter"}

        # Exchange code for tokens
        oauth_response = _exchange_slack_code(code)

        if not oauth_response.get("ok"):
            error = oauth_response.get("error", "unknown_error")
            PrintStyle(font_color="red", padding=False).print(
                f"Slack OAuth failed: {error}"
            )
            return {"error": f"Slack OAuth failed: {error}"}

        # Extract user and team info
        slack_user_id = oauth_response.get("authed_user", {}).get("id", "")
        team = oauth_response.get("team", {})
        team_id = team.get("id", "")
        access_token = oauth_response.get("access_token", "")

        # Get the internal user from the session
        user = session.get("user")
        if not user:
            return {"error": "Not authenticated — log in first"}

        internal_user_id = user.get("id", "")

        # Link the Slack identity to the internal user
        _link_slack_user(internal_user_id, slack_user_id, team_id, access_token)

        return {
            "ok": True,
            "message": f"Slack account linked successfully (team: {team.get('name', team_id)})",
        }
