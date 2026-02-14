# tests/test_webhook_jira.py
"""Tests for the Jira Cloud webhook receiver API handler."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_request(
    data: dict,
    secret: str = "test-jira-secret",
    event_type: str = "jira:issue_created",
) -> MagicMock:
    """Create a mock Flask Request with Jira webhook headers."""
    body = json.dumps(data).encode()
    request = MagicMock()
    request.data = body
    request.get_json.return_value = data
    request.headers = {
        "X-Atlassian-Webhook-Identifier": "hook-123",
    }
    request.args = {"secret": secret}
    return request


class TestJiraWebhookImport:
    def test_handler_importable(self):
        from python.api.webhook_jira import WebhookJira

        assert WebhookJira is not None

    def test_requires_no_auth(self):
        from python.api.webhook_jira import WebhookJira

        assert WebhookJira.requires_auth() is False

    def test_requires_no_csrf(self):
        from python.api.webhook_jira import WebhookJira

        assert WebhookJira.requires_csrf() is False

    def test_post_only(self):
        from python.api.webhook_jira import WebhookJira

        assert WebhookJira.get_methods() == ["POST"]


class TestJiraSignatureRejection:
    @pytest.mark.asyncio
    async def test_rejects_invalid_secret(self):
        from python.api.webhook_jira import WebhookJira

        handler = WebhookJira(MagicMock(), MagicMock())
        data = {
            "webhookEvent": "jira:issue_created",
            "issue": {"key": "PROJ-1", "fields": {"summary": "Test"}},
        }
        request = _make_request(data, secret="wrong-secret")

        with patch(
            "python.api.webhook_jira._get_jira_webhook_secret",
            return_value="correct-secret",
        ):
            result = await handler.process({}, request)

        assert hasattr(result, "status_code")
        assert result.status_code == 403


class TestJiraIssueEvents:
    @pytest.mark.asyncio
    async def test_issue_created_triggers_processing(self):
        from python.api.webhook_jira import WebhookJira

        handler = WebhookJira(MagicMock(), MagicMock())
        data = {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "key": "PROJ-42",
                "fields": {
                    "summary": "Bug in production",
                    "description": "Something is broken",
                    "priority": {"name": "High"},
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Bug"},
                    "labels": [],
                    "reporter": {
                        "accountId": "abc123",
                        "displayName": "Test User",
                    },
                },
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_jira._get_jira_webhook_secret",
                return_value="test-jira-secret",
            ),
            patch(
                "python.api.webhook_jira.WebhookJira._process_jira_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_issue_updated_with_label_triggers_processing(self):
        from python.api.webhook_jira import WebhookJira

        handler = WebhookJira(MagicMock(), MagicMock())
        data = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-10",
                "fields": {
                    "summary": "Feature request",
                    "description": "Add dark mode",
                    "priority": {"name": "Medium"},
                    "status": {"name": "To Do"},
                    "issuetype": {"name": "Story"},
                    "labels": ["apollos-ai"],
                    "reporter": {
                        "accountId": "def456",
                        "displayName": "Another User",
                    },
                },
            },
            "changelog": {
                "items": [
                    {
                        "field": "labels",
                        "fromString": "",
                        "toString": "apollos-ai",
                    }
                ]
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_jira._get_jira_webhook_secret",
                return_value="test-jira-secret",
            ),
            patch(
                "python.api.webhook_jira.WebhookJira._process_jira_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()


class TestJiraCommentEvents:
    @pytest.mark.asyncio
    async def test_comment_created_triggers_processing(self):
        from python.api.webhook_jira import WebhookJira

        handler = WebhookJira(MagicMock(), MagicMock())
        data = {
            "webhookEvent": "comment_created",
            "comment": {
                "body": "@apollos-ai please investigate",
                "author": {
                    "accountId": "user-789",
                    "displayName": "Commenter",
                },
            },
            "issue": {
                "key": "PROJ-5",
                "fields": {
                    "summary": "Test issue",
                    "description": "body text",
                    "priority": {"name": "Low"},
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Task"},
                    "labels": [],
                    "reporter": {
                        "accountId": "abc",
                        "displayName": "Reporter",
                    },
                },
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_jira._get_jira_webhook_secret",
                return_value="test-jira-secret",
            ),
            patch(
                "python.api.webhook_jira.WebhookJira._process_jira_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()


class TestJiraIgnoredEvents:
    @pytest.mark.asyncio
    async def test_unhandled_event_type_returns_ok(self):
        from python.api.webhook_jira import WebhookJira

        handler = WebhookJira(MagicMock(), MagicMock())
        data = {"webhookEvent": "jira:issue_deleted", "issue": {"key": "X-1"}}
        request = _make_request(data)

        with patch(
            "python.api.webhook_jira._get_jira_webhook_secret",
            return_value="test-jira-secret",
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_issue_updated_without_label_change_ignored(self):
        from python.api.webhook_jira import WebhookJira

        handler = WebhookJira(MagicMock(), MagicMock())
        data = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-99",
                "fields": {
                    "summary": "Updated issue",
                    "description": "",
                    "priority": {"name": "Low"},
                    "status": {"name": "Done"},
                    "issuetype": {"name": "Task"},
                    "labels": [],
                    "reporter": {"accountId": "x", "displayName": "X"},
                },
            },
            "changelog": {
                "items": [
                    {
                        "field": "status",
                        "fromString": "Open",
                        "toString": "Done",
                    }
                ]
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_jira._get_jira_webhook_secret",
                return_value="test-jira-secret",
            ),
            patch(
                "python.api.webhook_jira.WebhookJira._process_jira_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_not_called()
