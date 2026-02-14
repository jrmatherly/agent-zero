"""Webhook event log API — returns recent inbound webhook events.

Auto-discovered at GET /webhook_events_get.

Query parameters:
- limit: Maximum number of events to return (default 50)
- source: Filter by platform (slack, github, jira)
"""

from python.helpers.api import ApiHandler, Request
from python.helpers.webhook_event_log import WebhookEventLog


class WebhookEventsGet(ApiHandler):
    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET"]

    async def process(self, input: dict, request: Request) -> dict:
        log = WebhookEventLog.get_instance()

        limit = int(request.args.get("limit", "50"))
        source = request.args.get("source")

        events = log.recent(limit=limit, source=source)
        return {"events": events}
