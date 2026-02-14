"""Shared models for platform integrations (Slack, GitHub, Jira).

Defines the normalized message format, webhook context, and callback
registration used by all webhook handlers and the callback processor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    SLACK = "slack"
    GITHUB = "github"
    JIRA = "jira"
    INTERNAL = "internal"


class IntegrationMessage(BaseModel):
    """Normalized inbound message from any platform."""

    source: SourceType
    text: str
    external_user_id: str
    external_user_name: str | None = None
    external_message_id: str | None = None
    thread_id: str | None = None
    channel_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookContext(BaseModel):
    """Captures where a webhook came from so callbacks can reply."""

    source: SourceType
    channel_id: str | None = None
    thread_id: str | None = None
    team_id: str | None = None
    response_url: str | None = None
    metadata: dict = Field(default_factory=dict)

    def callback_key(self) -> str:
        """Stable key for deduplication and lookup."""
        parts = [self.source, self.channel_id or "", self.thread_id or ""]
        return ":".join(parts)


class CallbackStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    AWAITING_APPROVAL = "awaiting_approval"


class CallbackRegistration(BaseModel):
    """Tracks a pending callback delivery for a conversation."""

    conversation_id: str
    webhook_context: WebhookContext
    status: CallbackStatus = CallbackStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
