# tests/test_plan_approval.py
"""Tests for human-in-the-loop plan approval workflow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAwaitingApprovalStatus:
    def test_awaiting_approval_status_exists(self):
        from python.helpers.integration_models import CallbackStatus

        assert hasattr(CallbackStatus, "AWAITING_APPROVAL")
        assert CallbackStatus.AWAITING_APPROVAL == "awaiting_approval"


class TestCallbackRegistryApprovalMethods:
    def test_list_awaiting_approval(self):
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
            conversation_id="approval-test-1",
            webhook_context=ctx,
            status=CallbackStatus.AWAITING_APPROVAL,
        )
        registry.register("approval-test-1", reg)

        # Add a non-approval callback
        reg2 = CallbackRegistration(
            conversation_id="approval-test-2",
            webhook_context=ctx,
            status=CallbackStatus.PENDING,
        )
        registry.register("approval-test-2", reg2)

        awaiting = registry.list_awaiting_approval()
        assert len(awaiting) == 1
        assert awaiting[0].conversation_id == "approval-test-1"

    def test_list_all_returns_all_registrations(self):
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(source=SourceType.SLACK, channel_id="C123")
        for i in range(3):
            reg = CallbackRegistration(
                conversation_id=f"list-all-{i}",
                webhook_context=ctx,
                status=CallbackStatus.PENDING,
            )
            registry.register(f"list-all-{i}", reg)

        all_regs = registry.list_all()
        assert len(all_regs) == 3


class TestApprovalWebhookHandling:
    @pytest.mark.asyncio
    async def test_approval_comment_transitions_to_pending(self):
        """When an approval comment arrives, status should go from
        AWAITING_APPROVAL to PENDING so the callback extension picks it up."""
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(
            source=SourceType.GITHUB,
            channel_id="owner/repo",
            metadata={"issue_number": 42, "event_type": "issues"},
        )
        reg = CallbackRegistration(
            conversation_id="github:owner/repo:issue:42",
            webhook_context=ctx,
            status=CallbackStatus.AWAITING_APPROVAL,
        )
        registry.register("github:owner/repo:issue:42", reg)

        # Simulate approval
        registry.update_status("github:owner/repo:issue:42", CallbackStatus.PENDING)

        updated = registry.get("github:owner/repo:issue:42")
        assert updated is not None
        assert updated.status == CallbackStatus.PENDING

    @pytest.mark.asyncio
    async def test_callback_extension_skips_awaiting_approval(self):
        """The callback extension should not fire for AWAITING_APPROVAL status."""
        from python.extensions.monologue_end._80_integration_callback import (
            IntegrationCallback,
        )
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            CallbackStatus,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(
            source=SourceType.SLACK,
            channel_id="C123",
        )
        reg = CallbackRegistration(
            conversation_id="ctx-skip-approval",
            webhook_context=ctx,
            status=CallbackStatus.AWAITING_APPROVAL,
        )
        registry.register("ctx-skip-approval", reg)

        agent = MagicMock()
        agent.number = 0
        agent.context = MagicMock()
        agent.context.id = "ctx-skip-approval"

        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_callback",
                new_callable=AsyncMock,
            ) as mock_deliver,
        ):
            await ext.execute(loop_data=MagicMock())

        # Should NOT have called _deliver_callback because status is AWAITING_APPROVAL
        mock_deliver.assert_not_called()
        # Status should remain unchanged
        assert reg.status == CallbackStatus.AWAITING_APPROVAL
