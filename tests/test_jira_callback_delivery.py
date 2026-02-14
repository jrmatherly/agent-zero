# tests/test_jira_callback_delivery.py
"""Tests for Jira-specific callback delivery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestJiraDeliveryRouting:
    @pytest.mark.asyncio
    async def test_jira_source_routes_to_jira_delivery(self):
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
            source=SourceType.JIRA,
            channel_id="PROJ",
            metadata={
                "issue_key": "PROJ-42",
                "event_type": "jira:issue_created",
            },
        )
        reg = CallbackRegistration(
            conversation_id="ctx-jira-deliver", webhook_context=ctx
        )
        registry.register("ctx-jira-deliver", reg)

        agent = MagicMock()
        agent.number = 0
        agent.context = MagicMock()
        agent.context.id = "ctx-jira-deliver"
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "I analyzed the Jira issue and found the root cause."
        agent.history = [msg]

        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_jira",
                new_callable=AsyncMock,
            ) as mock_jira,
        ):
            await ext.execute(loop_data=MagicMock())

        mock_jira.assert_called_once()
        assert reg.status == CallbackStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_jira_delivery_receives_summary_and_reg(self):
        from python.extensions.monologue_end._80_integration_callback import (
            IntegrationCallback,
        )
        from python.helpers.callback_registry import CallbackRegistry
        from python.helpers.integration_models import (
            CallbackRegistration,
            SourceType,
            WebhookContext,
        )

        registry = CallbackRegistry()
        ctx = WebhookContext(
            source=SourceType.JIRA,
            channel_id="PROJ",
            metadata={"issue_key": "PROJ-10"},
        )
        reg = CallbackRegistration(conversation_id="ctx-jira-args", webhook_context=ctx)
        registry.register("ctx-jira-args", reg)

        agent = MagicMock()
        agent.number = 0
        agent.context = MagicMock()
        agent.context.id = "ctx-jira-args"
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "Completed the Jira task."
        agent.history = [msg]

        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_jira",
                new_callable=AsyncMock,
            ) as mock_jira,
        ):
            await ext.execute(loop_data=MagicMock())

        # Verify it received the registration and a summary string
        args = mock_jira.call_args
        assert args[0][0] is reg
        assert isinstance(args[0][1], str)
        assert "Completed the Jira task" in args[0][1]
