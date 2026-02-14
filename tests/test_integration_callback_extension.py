# tests/test_integration_callback_extension.py
"""Tests for the integration callback monologue_end extension."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_agent_mock(context_id="ctx-test"):
    """Create a minimal Agent mock for extension tests."""
    agent = MagicMock()
    agent.number = 0  # Main agent
    agent.context = MagicMock()
    agent.context.id = context_id
    agent.context.user_id = "user-1"
    agent.history = []
    return agent


def _make_loop_data():
    """Create a minimal LoopData-like object."""
    ld = MagicMock()
    ld.iteration = 3
    ld.user_message = "fix the bug"
    return ld


class TestCallbackExtensionSkips:
    @pytest.mark.asyncio
    async def test_skips_subordinate_agents(self):
        from python.extensions.monologue_end._80_integration_callback import (
            IntegrationCallback,
        )

        agent = _make_agent_mock()
        agent.number = 1  # Subordinate, not main
        ext = IntegrationCallback(agent)
        # Should return without error (no callback check needed)
        await ext.execute(loop_data=_make_loop_data())

    @pytest.mark.asyncio
    async def test_skips_when_no_callback_registered(self):
        from python.extensions.monologue_end._80_integration_callback import (
            IntegrationCallback,
        )
        from python.helpers.callback_registry import CallbackRegistry

        agent = _make_agent_mock(context_id="no-callback")
        registry = CallbackRegistry()
        ext = IntegrationCallback(agent)

        with patch(
            "python.extensions.monologue_end._80_integration_callback.CallbackRegistry.get_instance",
            return_value=registry,
        ):
            await ext.execute(loop_data=_make_loop_data())
        # No error, no side effects


class TestCallbackExtensionFires:
    @pytest.mark.asyncio
    async def test_fires_callback_for_registered_conversation(self):
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
        ctx = WebhookContext(source=SourceType.SLACK, channel_id="C1", thread_id="t1")
        reg = CallbackRegistration(conversation_id="ctx-fire", webhook_context=ctx)
        registry.register("ctx-fire", reg)

        agent = _make_agent_mock(context_id="ctx-fire")
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
            await ext.execute(loop_data=_make_loop_data())

        mock_deliver.assert_called_once()
        assert reg.status == CallbackStatus.COMPLETED
