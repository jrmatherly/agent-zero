# tests/test_webhook_event_log.py
"""Tests for webhook event logging."""

from unittest.mock import MagicMock, patch

import pytest


class TestWebhookEventLogImport:
    def test_module_importable(self):
        from python.helpers.webhook_event_log import WebhookEventLog

        assert WebhookEventLog is not None


class TestWebhookEventLogStorage:
    def test_log_event(self):
        from python.helpers.webhook_event_log import WebhookEventLog

        log = WebhookEventLog()
        log.record(
            source="github",
            event_type="issues",
            action="opened",
            delivery_id="delivery-123",
            payload_summary={"repo": "owner/repo", "number": 42},
        )

        events = log.recent(limit=10)
        assert len(events) == 1
        assert events[0]["source"] == "github"
        assert events[0]["event_type"] == "issues"
        assert events[0]["delivery_id"] == "delivery-123"

    def test_recent_returns_newest_first(self):
        from python.helpers.webhook_event_log import WebhookEventLog

        log = WebhookEventLog()
        for i in range(5):
            log.record(
                source="slack",
                event_type="event_callback",
                action="app_mention",
                delivery_id=f"delivery-{i}",
            )

        events = log.recent(limit=3)
        assert len(events) == 3
        # Most recent should be first
        assert events[0]["delivery_id"] == "delivery-4"

    def test_max_entries_enforced(self):
        from python.helpers.webhook_event_log import WebhookEventLog

        log = WebhookEventLog(max_entries=5)
        for i in range(10):
            log.record(
                source="jira",
                event_type="jira:issue_created",
                action="created",
                delivery_id=f"d-{i}",
            )

        events = log.recent(limit=100)
        assert len(events) == 5

    def test_filter_by_source(self):
        from python.helpers.webhook_event_log import WebhookEventLog

        log = WebhookEventLog()
        log.record(source="github", event_type="issues", action="opened")
        log.record(source="slack", event_type="event_callback", action="app_mention")
        log.record(source="github", event_type="pull_request", action="opened")

        github_events = log.recent(limit=10, source="github")
        assert len(github_events) == 2
        assert all(e["source"] == "github" for e in github_events)


class TestWebhookEventLogApi:
    def test_handler_importable(self):
        from python.api.webhook_events_get import WebhookEventsGet

        assert WebhookEventsGet is not None

    @pytest.mark.asyncio
    async def test_returns_recent_events(self):
        from python.api.webhook_events_get import WebhookEventsGet
        from python.helpers.webhook_event_log import WebhookEventLog

        log = WebhookEventLog()
        log.record(
            source="github",
            event_type="issues",
            action="opened",
            delivery_id="test-delivery",
        )

        handler = WebhookEventsGet(MagicMock(), MagicMock())
        request = MagicMock()
        request.args = {}

        with patch(
            "python.api.webhook_events_get.WebhookEventLog.get_instance",
            return_value=log,
        ):
            result = await handler.process({}, request)

        assert "events" in result
        assert len(result["events"]) == 1
        assert result["events"][0]["source"] == "github"
