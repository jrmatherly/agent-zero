# tests/test_webhook_github.py
"""Tests for the GitHub webhook receiver API handler."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_github_signature(body: bytes, secret: str) -> str:
    """Generate a valid GitHub HMAC-SHA256 signature."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_request(
    data: dict,
    secret: str = "test-webhook-secret",
    event_type: str = "issues",
) -> MagicMock:
    """Create a mock Flask Request with GitHub headers."""
    body = json.dumps(data).encode()
    sig = _make_github_signature(body, secret)
    request = MagicMock()
    request.data = body
    request.get_json.return_value = data
    request.headers = {
        "X-Hub-Signature-256": sig,
        "X-GitHub-Event": event_type,
        "X-GitHub-Delivery": "delivery-123",
    }
    return request


class TestGitHubWebhookImport:
    def test_handler_importable(self):
        from python.api.webhook_github import WebhookGithub

        assert WebhookGithub is not None

    def test_requires_no_auth(self):
        from python.api.webhook_github import WebhookGithub

        assert WebhookGithub.requires_auth() is False

    def test_requires_no_csrf(self):
        from python.api.webhook_github import WebhookGithub

        assert WebhookGithub.requires_csrf() is False

    def test_post_only(self):
        from python.api.webhook_github import WebhookGithub

        assert WebhookGithub.get_methods() == ["POST"]


class TestGitHubSignatureRejection:
    @pytest.mark.asyncio
    async def test_rejects_invalid_signature(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {"action": "opened", "issue": {"number": 1}}
        request = _make_request(data, secret="wrong-secret")

        with patch(
            "python.api.webhook_github._get_github_webhook_secret",
            return_value="correct-secret",
        ):
            result = await handler.process({}, request)

        assert hasattr(result, "status_code")
        assert result.status_code == 403


class TestGitHubIssueEvents:
    @pytest.mark.asyncio
    async def test_issue_opened_triggers_processing(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Bug report",
                "body": "Something is broken",
                "user": {"login": "testuser", "id": 12345},
                "labels": [],
            },
            "repository": {
                "full_name": "owner/repo",
            },
        }
        request = _make_request(data, event_type="issues")

        with (
            patch(
                "python.api.webhook_github._get_github_webhook_secret",
                return_value="test-webhook-secret",
            ),
            patch(
                "python.api.webhook_github.WebhookGithub._process_github_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_issue_labeled_triggers_processing(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {
            "action": "labeled",
            "label": {"name": "apollos-ai"},
            "issue": {
                "number": 10,
                "title": "Feature request",
                "body": "Add dark mode",
                "user": {"login": "testuser", "id": 12345},
                "labels": [{"name": "apollos-ai"}],
            },
            "repository": {"full_name": "owner/repo"},
        }
        request = _make_request(data, event_type="issues")

        with (
            patch(
                "python.api.webhook_github._get_github_webhook_secret",
                return_value="test-webhook-secret",
            ),
            patch(
                "python.api.webhook_github.WebhookGithub._process_github_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()


class TestGitHubIssueCommentEvents:
    @pytest.mark.asyncio
    async def test_issue_comment_with_mention_triggers(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {
            "action": "created",
            "comment": {
                "body": "@apollos-ai please fix this",
                "user": {"login": "commenter", "id": 99},
            },
            "issue": {
                "number": 5,
                "title": "Test issue",
                "body": "body text",
                "user": {"login": "author", "id": 1},
                "labels": [],
            },
            "repository": {"full_name": "owner/repo"},
        }
        request = _make_request(data, event_type="issue_comment")

        with (
            patch(
                "python.api.webhook_github._get_github_webhook_secret",
                return_value="test-webhook-secret",
            ),
            patch(
                "python.api.webhook_github.WebhookGithub._process_github_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()


class TestGitHubPREvents:
    @pytest.mark.asyncio
    async def test_pr_opened_triggers_processing(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {
            "action": "opened",
            "pull_request": {
                "number": 7,
                "title": "Add feature",
                "body": "This PR adds a feature",
                "user": {"login": "dev", "id": 55},
            },
            "repository": {"full_name": "owner/repo"},
        }
        request = _make_request(data, event_type="pull_request")

        with (
            patch(
                "python.api.webhook_github._get_github_webhook_secret",
                return_value="test-webhook-secret",
            ),
            patch(
                "python.api.webhook_github.WebhookGithub._process_github_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()


class TestGitHubIgnoredEvents:
    @pytest.mark.asyncio
    async def test_unhandled_event_type_returns_ok(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {"action": "deleted", "repository": {"full_name": "owner/repo"}}
        request = _make_request(data, event_type="repository")

        with patch(
            "python.api.webhook_github._get_github_webhook_secret",
            return_value="test-webhook-secret",
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_issue_closed_action_ignored(self):
        from python.api.webhook_github import WebhookGithub

        handler = WebhookGithub(MagicMock(), MagicMock())
        data = {
            "action": "closed",
            "issue": {
                "number": 1,
                "title": "Old issue",
                "body": "",
                "user": {"login": "u", "id": 1},
                "labels": [],
            },
            "repository": {"full_name": "owner/repo"},
        }
        request = _make_request(data, event_type="issues")

        with (
            patch(
                "python.api.webhook_github._get_github_webhook_secret",
                return_value="test-webhook-secret",
            ),
            patch(
                "python.api.webhook_github.WebhookGithub._process_github_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_not_called()
