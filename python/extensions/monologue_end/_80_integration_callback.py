"""Fire integration callbacks when the agent's monologue completes.

Checks the CallbackRegistry for a pending callback matching this
conversation. If found, marks it PROCESSING and schedules delivery
back to the originating platform via MCP tools.
"""

from agent import LoopData
from python.helpers.callback_registry import CallbackRegistry
from python.helpers.extension import Extension
from python.helpers.integration_models import CallbackStatus
from python.helpers.log import Log


class IntegrationCallback(Extension):
    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        # Only fire for the main agent (agent 0), not subordinates
        if self.agent.number != 0:
            return

        registry = CallbackRegistry.get_instance()
        reg = registry.get(self.agent.context.id)
        if not reg or reg.status != CallbackStatus.PENDING:
            return

        # Mark as processing to prevent duplicate delivery
        registry.update_status(self.agent.context.id, CallbackStatus.PROCESSING)

        try:
            await self._deliver_callback(reg, loop_data)
            registry.update_status(self.agent.context.id, CallbackStatus.COMPLETED)
        except Exception as e:
            registry.increment_attempts(self.agent.context.id, error=str(e))
            registry.update_status(self.agent.context.id, CallbackStatus.ERROR)
            Log.error(f"Integration callback failed for {self.agent.context.id}: {e}")

    async def _deliver_callback(self, reg, loop_data):
        """Deliver the callback to the originating platform.

        This is a dispatcher -- routes to the appropriate platform-specific
        delivery method. Platform integrations (Phase 2-4) will implement
        the actual MCP tool calls.
        """
        source = reg.webhook_context.source
        summary = self._extract_summary(loop_data)

        # Platform-specific delivery will be added in Phase 2-4
        # For now, log the callback
        Log.info(
            f"Integration callback ready: source={source}, "
            f"conversation={reg.conversation_id}, "
            f"summary_length={len(summary)}"
        )

    def _extract_summary(self, loop_data) -> str:
        """Extract a summary from the agent's last response."""
        if hasattr(self.agent, "history") and self.agent.history:
            for msg in reversed(self.agent.history):
                if hasattr(msg, "role") and msg.role == "assistant":
                    content = getattr(msg, "content", "")
                    if isinstance(content, str) and content.strip():
                        return content[:4000]
        return "Agent completed the task."
