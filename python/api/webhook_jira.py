"""Jira Cloud webhook receiver — accepts Jira webhook payloads.

Auto-discovered at POST /webhook_jira.

Handles:
- jira:issue_created
- jira:issue_updated (when "apollos-ai" label is added)
- comment_created
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
from python.helpers.webhook_verify import verify_jira_signature

# Events we care about
_HANDLED_EVENTS = {"jira:issue_created", "jira:issue_updated", "comment_created"}


def _get_jira_webhook_secret() -> str:
    """Retrieve the Jira webhook secret from settings."""
    from python.helpers.settings import get_settings

    return get_settings().get("jira_webhook_secret", "")


def _has_label_change(data: dict) -> bool:
    """Check if the changelog contains a label addition."""
    changelog = data.get("changelog", {})
    for item in changelog.get("items", []):
        if item.get("field") == "labels" and item.get("toString"):
            return True
    return False


class WebhookJira(ApiHandler):
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
        # Jira sends the shared secret as a query parameter
        provided_secret = request.args.get("secret", "")
        expected_secret = _get_jira_webhook_secret()

        if not verify_jira_signature(provided_secret, expected_secret):
            return Response("Invalid signature", status=403)

        data = request.get_json()
        event_type = data.get("webhookEvent", "")

        should_process = False

        if event_type == "jira:issue_created":
            should_process = True
        elif event_type == "jira:issue_updated" and _has_label_change(data):
            should_process = True
        elif event_type == "comment_created":
            should_process = True

        if should_process:
            await self._process_jira_event(event_type, data)

        return {"ok": True}

    async def _process_jira_event(self, event_type: str, data: dict) -> None:
        """Process a Jira event by creating an IntegrationMessage."""
        from python.helpers.callback_registry import CallbackRegistry

        issue = data.get("issue", {})
        fields = issue.get("fields", {})
        issue_key = issue.get("key", "")

        # Extract reporter info
        reporter = fields.get("reporter", {})
        user_id = reporter.get("accountId", "")
        user_name = reporter.get("displayName", "")

        # For comments, use the comment author and body
        if event_type == "comment_created":
            comment = data.get("comment", {})
            body = comment.get("body", "")
            author = comment.get("author", {})
            user_id = author.get("accountId", "")
            user_name = author.get("displayName", "")
        else:
            body = fields.get("description", "") or ""

        message = IntegrationMessage(
            source=SourceType.JIRA,
            text=body,
            external_user_id=user_id,
            external_user_name=user_name,
            channel_id=issue_key.split("-")[0] if "-" in issue_key else issue_key,
            metadata={
                "event_type": event_type,
                "issue_key": issue_key,
                "summary": fields.get("summary", ""),
                "priority": fields.get("priority", {}).get("name", ""),
                "status": fields.get("status", {}).get("name", ""),
                "issue_type": fields.get("issuetype", {}).get("name", ""),
            },
        )

        webhook_ctx = WebhookContext(
            source=SourceType.JIRA,
            channel_id=message.channel_id,
            metadata={
                "issue_key": issue_key,
                "event_type": event_type,
            },
        )

        callback = CallbackRegistration(
            conversation_id=f"jira:{issue_key}",
            webhook_context=webhook_ctx,
        )
        registry = CallbackRegistry.get_instance()
        registry.register(callback.conversation_id, callback)

        PrintStyle(font_color="cyan", padding=False).print(
            f"Jira event: {event_type} on {issue_key}"
        )
