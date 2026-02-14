# tests/test_callback_registry.py
"""Tests for the callback registry."""


class TestCallbackRegistry:
    def test_register_and_get(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.SLACK, channel_id="C1", thread_id="t1")
        reg = CallbackRegistration(conversation_id="conv-1", webhook_context=ctx)
        registry.register("conv-1", reg)

        result = registry.get("conv-1")
        assert result is not None
        assert result.conversation_id == "conv-1"
        assert result.status == CallbackStatus.PENDING

    def test_get_missing_returns_none(self):
        from python.helpers.callback_registry import CallbackRegistry

        registry = CallbackRegistry()
        assert registry.get("nonexistent") is None

    def test_update_status(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.GITHUB, channel_id="repo")
        reg = CallbackRegistration(conversation_id="conv-2", webhook_context=ctx)
        registry.register("conv-2", reg)

        registry.update_status("conv-2", CallbackStatus.COMPLETED)
        result = registry.get("conv-2")
        assert result.status == CallbackStatus.COMPLETED

    def test_remove(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.JIRA, channel_id="PROJ")
        reg = CallbackRegistration(conversation_id="conv-3", webhook_context=ctx)
        registry.register("conv-3", reg)

        registry.remove("conv-3")
        assert registry.get("conv-3") is None

    def test_list_pending(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        for i in range(3):
            ctx = WebhookContext(source=SourceType.SLACK, channel_id=f"C{i}")
            reg = CallbackRegistration(conversation_id=f"conv-{i}", webhook_context=ctx)
            registry.register(f"conv-{i}", reg)

        registry.update_status("conv-1", CallbackStatus.COMPLETED)

        pending = registry.list_pending()
        assert len(pending) == 2
        assert all(r.status == CallbackStatus.PENDING for r in pending)

    def test_singleton(self):
        from python.helpers.callback_registry import CallbackRegistry

        a = CallbackRegistry.get_instance()
        b = CallbackRegistry.get_instance()
        assert a is b

    def test_increment_attempts(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.SLACK, channel_id="C1")
        reg = CallbackRegistration(conversation_id="conv-4", webhook_context=ctx)
        registry.register("conv-4", reg)

        registry.increment_attempts("conv-4", error="timeout")
        result = registry.get("conv-4")
        assert result.attempts == 1
        assert result.last_error == "timeout"
