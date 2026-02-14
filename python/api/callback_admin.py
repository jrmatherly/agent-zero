"""Admin API for managing integration callbacks.

Auto-discovered at POST /callback_admin.

Actions:
- list: List all callbacks with their status
- retry: Retry a specific failed callback
"""

from python.helpers.api import ApiHandler, Request
from python.helpers.callback_registry import CallbackRegistry
from python.helpers.callback_retry import schedule_retry


class CallbackAdmin(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: dict, request: Request) -> dict:
        data = request.get_json()
        action = data.get("action", "")
        registry = CallbackRegistry.get_instance()

        if action == "list":
            return self._list_callbacks(registry)
        elif action == "retry":
            return self._retry_callback(registry, data.get("conversation_id", ""))

        return {"error": f"Unknown action: {action}"}

    def _list_callbacks(self, registry: CallbackRegistry) -> dict:
        callbacks = registry.list_all()
        return {
            "callbacks": [
                {
                    "conversation_id": reg.conversation_id,
                    "source": reg.webhook_context.source,
                    "status": reg.status,
                    "attempts": reg.attempts,
                    "last_error": reg.last_error,
                    "created_at": reg.created_at.isoformat(),
                }
                for reg in callbacks
            ]
        }

    def _retry_callback(self, registry: CallbackRegistry, conversation_id: str) -> dict:
        if not conversation_id:
            return {"error": "Missing conversation_id"}

        reg = registry.get(conversation_id)
        if not reg:
            return {"error": f"Callback not found: {conversation_id}"}

        result = schedule_retry(registry, conversation_id)
        if result:
            return {"ok": True, "message": f"Retry scheduled for {conversation_id}"}
        return {"ok": False, "message": "Max retry attempts reached"}
