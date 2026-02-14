"""Slack webhook receiver — accepts Slack Events API payloads.

Auto-discovered at POST /webhook_slack.

Handles:
- url_verification (Slack app setup challenge)
- event_callback with app_mention or DM messages
"""

import time

from flask import Response
from python.helpers.integration_models import (
    CallbackRegistration,
    IntegrationMessage,
    SourceType,
    WebhookContext,
)
from python.helpers.webhook_verify import verify_slack_signature

from python.helpers.api import ApiHandler, Request
from python.helpers.print_style import PrintStyle

# Simple in-memory dedup cache: event_id -> timestamp
# Entries expire after _DEDUP_TTL_SECONDS
_event_dedup_cache: dict[str, float] = {}
_DEDUP_TTL_SECONDS = 300  # 5 minutes


def _get_slack_signing_secret() -> str:
    """Retrieve the Slack signing secret from settings."""
    from python.helpers.settings import get_settings

    return get_settings().get("slack_signing_secret", "")


def _is_duplicate_event(event_id: str) -> bool:
    """Check if we've already processed this event (and prune stale entries)."""
    now = time.time()
    # Prune expired entries
    expired = [k for k, v in _event_dedup_cache.items() if now - v > _DEDUP_TTL_SECONDS]
    for k in expired:
        del _event_dedup_cache[k]

    if event_id in _event_dedup_cache:
        return True
    _event_dedup_cache[event_id] = now
    return False


class WebhookSlack(ApiHandler):
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
        signing_secret = _get_slack_signing_secret()

        # Verify Slack signature
        if not verify_slack_signature(
            raw_body,
            request.headers.get("X-Slack-Signature"),
            request.headers.get("X-Slack-Request-Timestamp"),
            signing_secret,
        ):
            return Response("Invalid signature", status=403)

        data = request.get_json()

        # Handle URL verification challenge (Slack app setup)
        if data.get("type") == "url_verification":
            return {"challenge": data["challenge"]}

        # Handle event callbacks
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            event_id = data.get("event_id", "")

            # Dedup: skip if we've already processed this event
            if event_id and _is_duplicate_event(event_id):
                PrintStyle(font_color="cyan", padding=False).print(
                    f"Slack: duplicate event {event_id}, skipping"
                )
                return {"ok": True}

            # Ignore bot messages to prevent loops
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return {"ok": True}

            # Process app_mention or DM messages
            event_type = event.get("type", "")
            if event_type == "app_mention" or (
                event_type == "message" and event.get("channel_type") == "im"
            ):
                await self._process_slack_event(event, data)

        return {"ok": True}

    async def _process_slack_event(self, event: dict, data: dict) -> None:
        """Process a Slack event by creating an IntegrationMessage and routing to agent."""
        from python.helpers.callback_registry import CallbackRegistry

        message = IntegrationMessage(
            source=SourceType.SLACK,
            text=event.get("text", ""),
            external_user_id=event.get("user", ""),
            external_message_id=event.get("ts", ""),
            thread_id=event.get("thread_ts", event.get("ts", "")),
            channel_id=event.get("channel", ""),
            metadata={
                "team_id": data.get("team_id", ""),
                "event_type": event.get("type", ""),
            },
        )

        webhook_ctx = WebhookContext(
            source=SourceType.SLACK,
            channel_id=message.channel_id,
            thread_id=message.thread_id,
            team_id=data.get("team_id"),
            metadata={"event_id": data.get("event_id", "")},
        )

        # Register callback for when agent completes
        callback = CallbackRegistration(
            conversation_id=f"slack:{message.channel_id}:{message.thread_id}",
            webhook_context=webhook_ctx,
        )
        registry = CallbackRegistry.get_instance()
        registry.register(callback.conversation_id, callback)

        PrintStyle(font_color="cyan", padding=False).print(
            f"Slack event received: type={event.get('type')}, "
            f"channel={message.channel_id}, user={message.external_user_id}"
        )

        # Agent routing will be wired in when the full message loop
        # integration is implemented. For now, the callback is registered
        # and will be picked up by the monologue_end extension.
