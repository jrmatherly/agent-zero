# tests/test_callback_retry.py
"""Tests for callback retry logic with exponential backoff."""

from unittest.mock import MagicMock, patch

import pytest


class TestRetryHelperImport:
    def test_module_importable(self):
        from python.helpers.callback_retry import schedule_retry

        assert callable(schedule_retry)


class TestRetryLogic:
    def test_max_attempts_default(self):
        from python.helpers.callback_retry import MAX_RETRY_ATTEMPTS

        assert MAX_RETRY_ATTEMPTS == 3

    def test_backoff_delay_increases(self):
        from python.helpers.callback_retry import get_backoff_delay

        delay_1 = get_backoff_delay(attempt=1)
        delay_2 = get_backoff_delay(attempt=2)
        delay_3 = get_backoff_delay(attempt=3)

        assert delay_1 < delay_2 < delay_3

    def test_backoff_delay_first_attempt(self):
        from python.helpers.callback_retry import get_backoff_delay

        # First attempt should have a base delay
        delay = get_backoff_delay(attempt=1)
        assert delay >= 1  # at least 1 second

    def test_backoff_delay_capped(self):
        from python.helpers.callback_retry import get_backoff_delay

        # Even large attempt numbers should be capped
        delay = get_backoff_delay(attempt=100)
        assert delay <= 300  # max 5 minutes


class TestRetryScheduling:
    @pytest.mark.asyncio
    async def test_schedule_retry_increments_attempts(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.callback_retry import schedule_retry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.SLACK, channel_id="C123")
        reg = CallbackRegistration(
            conversation_id="retry-test-1",
            webhook_context=ctx,
            status=CallbackStatus.ERROR,
            attempts=1,
            last_error="Connection timeout",
        )
        registry.register("retry-test-1", reg)

        # schedule_retry should mark as PENDING for retry
        schedule_retry(registry, "retry-test-1")

        updated = registry.get("retry-test-1")
        assert updated is not None
        assert updated.status == CallbackStatus.PENDING

    @pytest.mark.asyncio
    async def test_schedule_retry_does_not_retry_past_max(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.callback_retry import MAX_RETRY_ATTEMPTS, schedule_retry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.SLACK, channel_id="C123")
        reg = CallbackRegistration(
            conversation_id="retry-test-max",
            webhook_context=ctx,
            status=CallbackStatus.ERROR,
            attempts=MAX_RETRY_ATTEMPTS,
            last_error="Permanent failure",
        )
        registry.register("retry-test-max", reg)

        # Should NOT retry — already at max
        result = schedule_retry(registry, "retry-test-max")
        assert result is False

        updated = registry.get("retry-test-max")
        assert updated is not None
        assert updated.status == CallbackStatus.ERROR


class TestCallbackRetryAdminApi:
    def test_admin_api_importable(self):
        from python.api.callback_admin import CallbackAdmin

        assert CallbackAdmin is not None

    @pytest.mark.asyncio
    async def test_list_action_returns_all_callbacks(self):
        from python.api.callback_admin import CallbackAdmin
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.GITHUB, channel_id="owner/repo")
        reg = CallbackRegistration(
            conversation_id="admin-list-1",
            webhook_context=ctx,
            status=CallbackStatus.ERROR,
            attempts=2,
            last_error="Failed",
        )
        registry.register("admin-list-1", reg)

        handler = CallbackAdmin(MagicMock(), MagicMock())
        request = MagicMock()
        request.get_json.return_value = {"action": "list"}

        with patch(
            "python.api.callback_admin.CallbackRegistry.get_instance",
            return_value=registry,
        ):
            result = await handler.process({}, request)

        assert "callbacks" in result
        assert len(result["callbacks"]) == 1
        assert result["callbacks"][0]["conversation_id"] == "admin-list-1"

    @pytest.mark.asyncio
    async def test_retry_action_retries_failed_callback(self):
        from python.api.callback_admin import CallbackAdmin
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.JIRA, channel_id="PROJ")
        reg = CallbackRegistration(
            conversation_id="admin-retry-1",
            webhook_context=ctx,
            status=CallbackStatus.ERROR,
            attempts=1,
            last_error="Timeout",
        )
        registry.register("admin-retry-1", reg)

        handler = CallbackAdmin(MagicMock(), MagicMock())
        request = MagicMock()
        request.get_json.return_value = {
            "action": "retry",
            "conversation_id": "admin-retry-1",
        }

        with patch(
            "python.api.callback_admin.CallbackRegistry.get_instance",
            return_value=registry,
        ):
            result = await handler.process({}, request)

        assert result["ok"] is True
        updated = registry.get("admin-retry-1")
        assert updated is not None
        assert updated.status == CallbackStatus.PENDING
