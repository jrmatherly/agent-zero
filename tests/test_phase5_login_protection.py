"""Tests for brute force login protection (Phase 5b.2).

Validates progressive delays, account lockout, lockout expiry,
and success-clears-history behavior.
"""

import time
from unittest.mock import patch

import pytest

from python.helpers.login_protection import LoginProtection


@pytest.fixture
def protection():
    """Fresh LoginProtection instance for each test."""
    return LoginProtection()


class TestProgressiveDelays:
    def test_first_failure_returns_zero_delay(self, protection):
        delay = protection.record_failure("alice")
        assert delay == 0

    def test_delays_increase_progressively(self, protection):
        delays = []
        for _ in range(5):
            delays.append(protection.record_failure("alice"))
        assert delays == [0, 1, 2, 4, 8]

    def test_delay_caps_at_max(self, protection):
        for _ in range(10):
            delay = protection.record_failure("alice")
        assert delay == 8  # stays at max


class TestAccountLockout:
    def test_not_locked_below_threshold(self, protection):
        for _ in range(4):
            protection.record_failure("bob")
        assert protection.check_locked("bob") is False

    def test_locked_at_threshold(self, protection):
        for _ in range(5):
            protection.record_failure("bob")
        assert protection.check_locked("bob") is True

    def test_lockout_remaining_returns_positive_when_locked(self, protection):
        for _ in range(5):
            protection.record_failure("bob")
        remaining = protection.lockout_remaining("bob")
        assert remaining > 0
        assert remaining <= 300

    def test_lockout_remaining_returns_zero_when_not_locked(self, protection):
        protection.record_failure("bob")
        assert protection.lockout_remaining("bob") == 0


class TestLockoutExpiry:
    def test_lockout_expires_after_duration(self, protection):
        for _ in range(5):
            protection.record_failure("carol")

        assert protection.check_locked("carol") is True

        # Simulate time passing beyond lockout duration
        with patch.object(time, "monotonic", return_value=time.monotonic() + 301):
            assert protection.check_locked("carol") is False

    def test_attempts_pruned_after_lockout_window(self, protection):
        for _ in range(5):
            protection.record_failure("carol")

        # Simulate time passing beyond lockout duration
        future = time.monotonic() + 301
        with patch.object(time, "monotonic", return_value=future):
            protection.check_locked("carol")  # triggers cleanup
            # After cleanup, first failure should return delay 0
            delay = protection.record_failure("carol")
            assert delay == 0


class TestSuccessClearsHistory:
    def test_success_clears_failures(self, protection):
        for _ in range(4):
            protection.record_failure("dave")
        protection.record_success("dave")

        # Should not be locked and first failure returns 0
        assert protection.check_locked("dave") is False
        delay = protection.record_failure("dave")
        assert delay == 0

    def test_success_for_unknown_user_is_noop(self, protection):
        protection.record_success("unknown")  # should not raise


class TestIsolation:
    def test_different_users_are_independent(self, protection):
        for _ in range(5):
            protection.record_failure("eve")

        assert protection.check_locked("eve") is True
        assert protection.check_locked("frank") is False
