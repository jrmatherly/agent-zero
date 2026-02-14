# tests/test_github_callback_delivery.py
"""Tests for GitHub-specific callback delivery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGitHubDeliveryRouting:
    @pytest.mark.asyncio
    async def test_github_source_routes_to_github_delivery(self):
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
            source=SourceType.GITHUB,
            channel_id="owner/repo",
            metadata={
                "issue_number": 42,
                "event_type": "issues",
            },
        )
        reg = CallbackRegistration(
            conversation_id="ctx-gh-deliver", webhook_context=ctx
        )
        registry.register("ctx-gh-deliver", reg)

        agent = MagicMock()
        agent.number = 0
        agent.context = MagicMock()
        agent.context.id = "ctx-gh-deliver"
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "I fixed the issue by updating the config."
        agent.history = [msg]

        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_github",
                new_callable=AsyncMock,
            ) as mock_gh,
        ):
            await ext.execute(loop_data=MagicMock())

        mock_gh.assert_called_once()
        assert reg.status == CallbackStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_github_delivery_receives_summary_and_reg(self):
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
            source=SourceType.GITHUB,
            channel_id="owner/repo",
            metadata={"issue_number": 10},
        )
        reg = CallbackRegistration(conversation_id="ctx-gh-args", webhook_context=ctx)
        registry.register("ctx-gh-args", reg)

        agent = MagicMock()
        agent.number = 0
        agent.context = MagicMock()
        agent.context.id = "ctx-gh-args"
        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "Done with the task."
        agent.history = [msg]

        ext = IntegrationCallback(agent)

        with (
            patch(
                "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
                return_value=registry,
            ),
            patch(
                "python.extensions.monologue_end._80_integration_callback.IntegrationCallback._deliver_github",
                new_callable=AsyncMock,
            ) as mock_gh,
        ):
            await ext.execute(loop_data=MagicMock())

        # Verify it received the registration and a summary string
        args = mock_gh.call_args
        assert args[0][0] is reg
        assert isinstance(args[0][1], str)
        assert "Done with the task" in args[0][1]
