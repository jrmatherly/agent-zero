# tests/test_webhook_slack.py
"""Tests for the Slack webhook receiver API handler."""

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_slack_signature(body: bytes, secret: str, timestamp: str) -> str:
    """Generate a valid Slack signature for testing."""
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    return "v0=" + hmac.new(secret.encode(), sig_basestring, hashlib.sha256).hexdigest()


def _make_request(
    data: dict,
    secret: str = "test-signing-secret",
    timestamp: str | None = None,
) -> MagicMock:
    """Create a mock Flask Request with Slack headers."""
    if timestamp is None:
        timestamp = str(int(time.time()))
    body = json.dumps(data).encode()
    sig = _make_slack_signature(body, secret, timestamp)
    request = MagicMock()
    request.data = body
    request.get_json.return_value = data
    request.headers = {
        "X-Slack-Signature": sig,
        "X-Slack-Request-Timestamp": timestamp,
    }
    return request


class TestSlackWebhookImport:
    def test_handler_importable(self):
        from python.api.webhook_slack import WebhookSlack

        assert WebhookSlack is not None

    def test_requires_no_auth(self):
        from python.api.webhook_slack import WebhookSlack

        assert WebhookSlack.requires_auth() is False

    def test_requires_no_csrf(self):
        from python.api.webhook_slack import WebhookSlack

        assert WebhookSlack.requires_csrf() is False

    def test_post_only(self):
        from python.api.webhook_slack import WebhookSlack

        assert WebhookSlack.get_methods() == ["POST"]


class TestSlackUrlVerification:
    @pytest.mark.asyncio
    async def test_url_verification_returns_challenge(self):
        from python.api.webhook_slack import WebhookSlack

        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {"type": "url_verification", "challenge": "abc123"}
        request = _make_request(data)

        with patch(
            "python.api.webhook_slack._get_slack_signing_secret",
            return_value="test-signing-secret",
        ):
            result = await handler.process({}, request)

        assert result == {"challenge": "abc123"}


class TestSlackSignatureRejection:
    @pytest.mark.asyncio
    async def test_rejects_invalid_signature(self):
        from python.api.webhook_slack import WebhookSlack

        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {"type": "event_callback", "event": {"type": "app_mention"}}
        request = _make_request(data, secret="wrong-secret")

        with patch(
            "python.api.webhook_slack._get_slack_signing_secret",
            return_value="correct-secret",
        ):
            result = await handler.process({}, request)

        # Should return a 403 response
        assert hasattr(result, "status_code")
        assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_stale_timestamp(self):
        from python.api.webhook_slack import WebhookSlack

        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {"type": "event_callback", "event": {"type": "app_mention"}}
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        request = _make_request(data, timestamp=old_ts)

        with patch(
            "python.api.webhook_slack._get_slack_signing_secret",
            return_value="test-signing-secret",
        ):
            result = await handler.process({}, request)

        assert hasattr(result, "status_code")
        assert result.status_code == 403


class TestSlackEventProcessing:
    @pytest.mark.asyncio
    async def test_app_mention_triggers_processing(self):
        from python.api.webhook_slack import WebhookSlack

        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {
            "type": "event_callback",
            "team_id": "T1234",
            "event_id": "Ev1234",
            "event": {
                "type": "app_mention",
                "user": "U5678",
                "text": "<@BOT> help me",
                "channel": "C9012",
                "ts": "1234567890.123456",
                "thread_ts": "1234567890.000000",
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_slack._get_slack_signing_secret",
                return_value="test-signing-secret",
            ),
            patch(
                "python.api.webhook_slack.WebhookSlack._process_slack_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_dm_message_triggers_processing(self):
        from python.api.webhook_slack import WebhookSlack

        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {
            "type": "event_callback",
            "team_id": "T1234",
            "event_id": "Ev5678",
            "event": {
                "type": "message",
                "channel_type": "im",
                "user": "U5678",
                "text": "help me",
                "channel": "D9012",
                "ts": "1234567890.123456",
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_slack._get_slack_signing_secret",
                return_value="test-signing-secret",
            ),
            patch(
                "python.api.webhook_slack.WebhookSlack._process_slack_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self):
        from python.api.webhook_slack import WebhookSlack

        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {
            "type": "event_callback",
            "team_id": "T1234",
            "event_id": "Ev9012",
            "event": {
                "type": "message",
                "channel_type": "im",
                "bot_id": "B1234",
                "text": "bot message",
                "channel": "D9012",
                "ts": "1234567890.123456",
            },
        }
        request = _make_request(data)

        with (
            patch(
                "python.api.webhook_slack._get_slack_signing_secret",
                return_value="test-signing-secret",
            ),
            patch(
                "python.api.webhook_slack.WebhookSlack._process_slack_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            result = await handler.process({}, request)

        assert result == {"ok": True}
        mock_process.assert_not_called()


class TestSlackEventDedup:
    @pytest.mark.asyncio
    async def test_duplicate_event_ignored(self):
        from python.api.webhook_slack import WebhookSlack, _event_dedup_cache

        _event_dedup_cache.clear()
        handler = WebhookSlack(MagicMock(), MagicMock())
        data = {
            "type": "event_callback",
            "team_id": "T1234",
            "event_id": "Ev_DEDUP",
            "event": {
                "type": "app_mention",
                "user": "U5678",
                "text": "hello",
                "channel": "C9012",
                "ts": "111.111",
            },
        }
        request1 = _make_request(data)
        request2 = _make_request(data)

        with (
            patch(
                "python.api.webhook_slack._get_slack_signing_secret",
                return_value="test-signing-secret",
            ),
            patch(
                "python.api.webhook_slack.WebhookSlack._process_slack_event",
                new_callable=AsyncMock,
            ) as mock_process,
        ):
            await handler.process({}, request1)
            await handler.process({}, request2)

        # Should only process once despite two calls
        mock_process.assert_called_once()
