"""Retry logic for failed integration callback deliveries.

Provides exponential backoff scheduling and a maximum retry limit.
When a callback fails, schedule_retry() resets it to PENDING status
so the monologue_end extension will re-attempt delivery.
"""

from __future__ import annotations

from python.helpers.callback_registry import CallbackRegistry
from python.helpers.integration_models import CallbackStatus

MAX_RETRY_ATTEMPTS = 3
BASE_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 300  # 5 minutes


def get_backoff_delay(attempt: int) -> float:
    """Calculate exponential backoff delay for the given attempt number.

    Uses 2^attempt as the base, capped at MAX_DELAY_SECONDS.
    """
    delay = BASE_DELAY_SECONDS**attempt
    return min(delay, MAX_DELAY_SECONDS)


def schedule_retry(registry: CallbackRegistry, conversation_id: str) -> bool:
    """Schedule a retry for a failed callback.

    Returns True if the retry was scheduled, False if max attempts reached.
    """
    reg = registry.get(conversation_id)
    if not reg:
        return False

    if reg.attempts >= MAX_RETRY_ATTEMPTS:
        return False

    # Reset to PENDING so the extension picks it up again
    registry.update_status(conversation_id, CallbackStatus.PENDING)
    return True
