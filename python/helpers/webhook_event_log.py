"""Lightweight in-memory webhook event log for debugging and audit.

Stores recent inbound webhook events in a bounded deque. Events are
stored as dicts with source, event type, action, delivery ID, and
optional payload summary.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import ClassVar


class WebhookEventLog:
    """Bounded in-memory log of recent webhook events."""

    _instance: ClassVar[WebhookEventLog | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, max_entries: int = 1000) -> None:
        self._events: deque[dict] = deque(maxlen=max_entries)
        self._store_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> WebhookEventLog:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record(
        self,
        source: str,
        event_type: str,
        action: str = "",
        delivery_id: str = "",
        payload_summary: dict | None = None,
    ) -> None:
        """Record an inbound webhook event."""
        event = {
            "source": source,
            "event_type": event_type,
            "action": action,
            "delivery_id": delivery_id,
            "payload_summary": payload_summary or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._store_lock:
            self._events.append(event)

    def recent(
        self,
        limit: int = 50,
        source: str | None = None,
    ) -> list[dict]:
        """Return recent events, newest first.

        Args:
            limit: Maximum number of events to return.
            source: Optional filter by source platform.
        """
        with self._store_lock:
            events = list(self._events)

        # Newest first
        events.reverse()

        if source:
            events = [e for e in events if e["source"] == source]

        return events[:limit]
