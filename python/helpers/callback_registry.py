"""Thread-safe in-memory registry for integration callback tracking.

Stores CallbackRegistration objects keyed by conversation_id. When an
agent monologue completes, the monologue_end extension checks this
registry and fires the appropriate callback processor.
"""

from __future__ import annotations

import threading
from typing import ClassVar

from python.helpers.integration_models import (
    CallbackRegistration,
    CallbackStatus,
)


class CallbackRegistry:
    """Thread-safe registry for pending integration callbacks."""

    _instance: ClassVar[CallbackRegistry | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._store: dict[str, CallbackRegistration] = {}
        self._store_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CallbackRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(
        self, conversation_id: str, registration: CallbackRegistration
    ) -> None:
        with self._store_lock:
            self._store[conversation_id] = registration

    def get(self, conversation_id: str) -> CallbackRegistration | None:
        with self._store_lock:
            return self._store.get(conversation_id)

    def update_status(self, conversation_id: str, status: CallbackStatus) -> None:
        with self._store_lock:
            reg = self._store.get(conversation_id)
            if reg:
                reg.status = status

    def increment_attempts(
        self, conversation_id: str, error: str | None = None
    ) -> None:
        with self._store_lock:
            reg = self._store.get(conversation_id)
            if reg:
                reg.attempts += 1
                reg.last_error = error

    def remove(self, conversation_id: str) -> None:
        with self._store_lock:
            self._store.pop(conversation_id, None)

    def list_pending(self) -> list[CallbackRegistration]:
        with self._store_lock:
            return [
                r for r in self._store.values() if r.status == CallbackStatus.PENDING
            ]

    def list_awaiting_approval(self) -> list[CallbackRegistration]:
        with self._store_lock:
            return [
                r
                for r in self._store.values()
                if r.status == CallbackStatus.AWAITING_APPROVAL
            ]

    def list_all(self) -> list[CallbackRegistration]:
        with self._store_lock:
            return list(self._store.values())
