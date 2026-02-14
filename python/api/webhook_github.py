"""GitHub webhook receiver — accepts GitHub App webhook payloads.

Auto-discovered at POST /webhook_github.

Handles:
- issues (opened, labeled)
- issue_comment (created with @mention)
- pull_request (opened, review_requested)
- pull_request_review_comment (created)
"""

from flask import Response

from python.helpers.api import ApiHandler, Request
from python.helpers.integration_models import (
    CallbackRegistration,
    IntegrationMessage,
    SourceType,
    WebhookContext,
)
from python.helpers.print_style import PrintStyle
from python.helpers.webhook_verify import verify_github_signature

# Events and actions we care about
_ISSUE_ACTIONS = {"opened", "labeled"}
_PR_ACTIONS = {"opened", "review_requested"}


def _get_github_webhook_secret() -> str:
    """Retrieve the GitHub webhook secret from settings."""
    from python.helpers.settings import get_settings

    return get_settings().get("github_webhook_secret", "")


class WebhookGithub(ApiHandler):
    @classmethod
    def requires_auth(cls) -> bool:
        return False

    @classmethod
    def requires_csrf(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        raw_body = request.data
        secret = _get_github_webhook_secret()

        if not verify_github_signature(
            raw_body,
            request.headers.get("X-Hub-Signature-256"),
            secret,
        ):
            return Response("Invalid signature", status=403)

        data = request.get_json()
        event_type = request.headers.get("X-GitHub-Event", "")
        action = data.get("action", "")

        should_process = False

        if event_type == "issues" and action in _ISSUE_ACTIONS:
            should_process = True
        elif event_type == "issue_comment" and action == "created":
            should_process = True
        elif event_type == "pull_request" and action in _PR_ACTIONS:
            should_process = True
        elif event_type == "pull_request_review_comment" and action == "created":
            should_process = True

        if should_process:
            await self._process_github_event(event_type, action, data)

        return {"ok": True}

    async def _process_github_event(
        self, event_type: str, action: str, data: dict
    ) -> None:
        """Process a GitHub event by creating an IntegrationMessage."""
        from python.helpers.callback_registry import CallbackRegistry

        repo = data.get("repository", {}).get("full_name", "")

        # Extract context based on event type
        if event_type in ("issues", "issue_comment"):
            issue = data.get("issue", {})
            number = issue.get("number", 0)
            title = issue.get("title", "")
            body = issue.get("body", "")
            user = issue.get("user", {})
            item_type = "issue"

            # For comments, include comment body
            if event_type == "issue_comment":
                comment = data.get("comment", {})
                body = comment.get("body", "")
                user = comment.get("user", {})
        elif event_type in ("pull_request", "pull_request_review_comment"):
            pr = data.get("pull_request", {})
            number = pr.get("number", 0)
            title = pr.get("title", "")
            body = pr.get("body", "")
            user = pr.get("user", {})
            item_type = "pull_request"

            if event_type == "pull_request_review_comment":
                comment = data.get("comment", {})
                body = comment.get("body", "")
                user = comment.get("user", {})
        else:
            return

        message = IntegrationMessage(
            source=SourceType.GITHUB,
            text=body or "",
            external_user_id=str(user.get("id", "")),
            external_user_name=user.get("login", ""),
            channel_id=repo,
            metadata={
                "event_type": event_type,
                "action": action,
                "repo_full_name": repo,
                "number": number,
                "title": title,
                "item_type": item_type,
            },
        )

        webhook_ctx = WebhookContext(
            source=SourceType.GITHUB,
            channel_id=message.channel_id,
            metadata={
                "issue_number": number,
                "event_type": event_type,
                "item_type": item_type,
                "delivery_id": "",
            },
        )

        callback = CallbackRegistration(
            conversation_id=f"github:{message.channel_id}:{item_type}:{number}",
            webhook_context=webhook_ctx,
        )
        registry = CallbackRegistry.get_instance()
        registry.register(callback.conversation_id, callback)

        PrintStyle(font_color="cyan", padding=False).print(
            f"GitHub event: {event_type}/{action} on {repo}#{number}"
        )
