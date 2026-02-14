# tests/test_integration_models.py
"""Tests for integration message models."""

from datetime import datetime


class TestSourceType:
    def test_slack_source(self):
        from python.helpers.integration_models import SourceType

        assert SourceType.SLACK == "slack"

    def test_github_source(self):
        from python.helpers.integration_models import SourceType

        assert SourceType.GITHUB == "github"

    def test_jira_source(self):
        from python.helpers.integration_models import SourceType

        assert SourceType.JIRA == "jira"

    def test_internal_source(self):
        from python.helpers.integration_models import SourceType

        assert SourceType.INTERNAL == "internal"


class TestIntegrationMessage:
    def test_create_minimal(self):
        from python.helpers.integration_models import IntegrationMessage, SourceType

        msg = IntegrationMessage(
            source=SourceType.SLACK,
            text="Hello agent",
            external_user_id="U12345",
        )
        assert msg.source == SourceType.SLACK
        assert msg.text == "Hello agent"
        assert msg.external_user_id == "U12345"
        assert msg.external_message_id is None
        assert isinstance(msg.received_at, datetime)

    def test_create_full(self):
        from python.helpers.integration_models import IntegrationMessage, SourceType

        msg = IntegrationMessage(
            source=SourceType.GITHUB,
            text="Fix this bug",
            external_user_id="user123",
            external_user_name="octocat",
            external_message_id="issue-42",
            thread_id="PR-99",
            channel_id="jrmatherly/apollos-ai",
            metadata={"issue_number": 42, "action": "opened"},
        )
        assert msg.metadata["issue_number"] == 42
        assert msg.channel_id == "jrmatherly/apollos-ai"

    def test_message_serialization(self):
        from python.helpers.integration_models import IntegrationMessage, SourceType

        msg = IntegrationMessage(
            source=SourceType.SLACK,
            text="test",
            external_user_id="U1",
        )
        data = msg.model_dump()
        assert data["source"] == "slack"
        assert "received_at" in data

    def test_message_from_dict(self):
        from python.helpers.integration_models import IntegrationMessage, SourceType

        data = {
            "source": "slack",
            "text": "hello",
            "external_user_id": "U1",
        }
        msg = IntegrationMessage.model_validate(data)
        assert msg.source == SourceType.SLACK


class TestWebhookContext:
    def test_create(self):
        from python.helpers.integration_models import WebhookContext, SourceType

        ctx = WebhookContext(
            source=SourceType.SLACK,
            channel_id="C12345",
            thread_id="1234567890.123456",
            team_id="T12345",
            response_url=None,
        )
        assert ctx.source == SourceType.SLACK
        assert ctx.channel_id == "C12345"

    def test_callback_key(self):
        from python.helpers.integration_models import WebhookContext, SourceType

        ctx = WebhookContext(
            source=SourceType.GITHUB,
            channel_id="jrmatherly/apollos-ai",
            thread_id="issue-42",
        )
        key = ctx.callback_key()
        assert "github" in key
        assert "issue-42" in key


class TestCallbackRegistration:
    def test_create(self):
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        ctx = WebhookContext(
            source=SourceType.SLACK,
            channel_id="C12345",
            thread_id="t1",
        )
        reg = CallbackRegistration(
            conversation_id="ctx-abc",
            webhook_context=ctx,
        )
        assert reg.status == CallbackStatus.PENDING
        assert reg.conversation_id == "ctx-abc"
        assert reg.attempts == 0
