# tests/test_slack_callback_delivery.py
"""Tests for Slack-specific callback delivery via MCP outbound."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_agent_mock(context_id="ctx-slack"):
    agent = MagicMock()
    agent.number = 0
    agent.context = MagicMock()
    agent.context.id = context_id
    agent.history = []
    # Mock the MCP call method
    agent.call_utility_llm = AsyncMock()
    return agent


class TestSlackDeliveryRouting:
    @pytest.mark.asyncio
    async def test_slack_source_routes_to_slack_delivery(self):
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
            channel_id="C1234",
            thread_id="1234567890.000000",
            metadata={"bot_token_available": True},
        )
        reg = CallbackRegistration(
            conversation_id="ctx-slack-deliver", webhook_context=ctx
        )
        registry.register("ctx-slack-deliver", reg)

        agent = _make_agent_mock(context_id="ctx-slack-deliver")
        # Add a response to history
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "I fixed the bug by updating the config."
        agent.history = [msg]

        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_slack",
                new_callable=AsyncMock,
            ) as mock_slack,
        ):
            await ext.execute(loop_data=MagicMock())

        mock_slack.assert_called_once()
        assert reg.status == CallbackStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_non_slack_source_does_not_call_slack_delivery(self):
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
        ctx = WebhookContext(source=SourceType.GITHUB, channel_id="repo/issue/1")
        reg = CallbackRegistration(
            conversation_id="ctx-github-no-slack", webhook_context=ctx
        )
        registry.register("ctx-github-no-slack", reg)

        agent = _make_agent_mock(context_id="ctx-github-no-slack")
        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_slack",
                new_callable=AsyncMock,
            ) as mock_slack,
        ):
            await ext.execute(loop_data=MagicMock())

        mock_slack.assert_not_called()


class TestSlackDeliveryContent:
    @pytest.mark.asyncio
    async def test_extracts_summary_from_history(self):
        from python.extensions.monologue_end._80_integration_callback import (
            IntegrationCallback,
        )

        agent = _make_agent_mock()
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "Here is the answer to your question."
        agent.history = [msg]

        ext = IntegrationCallback(agent)
        summary = ext._extract_summary(MagicMock())
        assert "Here is the answer" in summary

    def test_extract_summary_fallback(self):
        from python.extensions.monologue_end._80_integration_callback import (
            IntegrationCallback,
        )

        agent = _make_agent_mock()
        agent.history = []
        ext = IntegrationCallback(agent)
        summary = ext._extract_summary(MagicMock())
        assert summary == "Agent completed the task."
