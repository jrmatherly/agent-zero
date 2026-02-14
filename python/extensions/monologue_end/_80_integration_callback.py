"""Fire integration callbacks when the agent's monologue completes.

Checks the CallbackRegistry for a pending callback matching this
conversation. If found, marks it PROCESSING and schedules delivery
back to the originating platform via MCP tools.
"""

from python.helpers.callback_registry import CallbackRegistry
from python.helpers.integration_models import CallbackStatus, SourceType

from agent import LoopData
from python.helpers.extension import Extension
from python.helpers.print_style import PrintStyle


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
            PrintStyle(font_color="red", padding=False).print(
                f"Integration callback failed for {self.agent.context.id}: {e}"
            )

    async def _deliver_callback(self, reg, loop_data):
        """Deliver the callback to the originating platform.

        Routes to the appropriate platform-specific delivery method.
        """
        source = reg.webhook_context.source
        summary = self._extract_summary(loop_data)

        if source == SourceType.SLACK:
            await self._deliver_slack(reg, summary)
        elif source == SourceType.GITHUB:
            await self._deliver_github(reg, summary)
        elif source == SourceType.JIRA:
            await self._deliver_jira(reg, summary)
        else:
            PrintStyle(font_color="cyan", padding=False).print(
                f"Integration callback ready: source={source}, "
                f"conversation={reg.conversation_id}, "
                f"summary_length={len(summary)}"
            )

    async def _deliver_slack(self, reg, summary: str):
        """Deliver callback to Slack via MCP tools or API."""
        channel = reg.webhook_context.channel_id
        thread_ts = reg.webhook_context.thread_id

        PrintStyle(font_color="cyan", padding=False).print(
            f"Slack callback: channel={channel}, "
            f"thread_ts={thread_ts}, summary_length={len(summary)}"
        )

        # MCP-based delivery will call slack_postMessage tool
        # For now, log the delivery. Phase 2 will wire in actual MCP calls
        # when Slack MCP server is configured.

    async def _deliver_github(self, reg, summary: str):
        """Deliver callback to GitHub (Phase 3)."""
        PrintStyle(font_color="cyan", padding=False).print(
            f"GitHub callback: conversation={reg.conversation_id}, "
            f"summary_length={len(summary)}"
        )

    async def _deliver_jira(self, reg, summary: str):
        """Deliver callback to Jira (Phase 4)."""
        PrintStyle(font_color="cyan", padding=False).print(
            f"Jira callback: conversation={reg.conversation_id}, "
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
