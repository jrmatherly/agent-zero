# tests/test_webhook_verify.py
"""Tests for webhook signature verification helpers."""

import hashlib
import hmac
import time


class TestGitHubSignature:
    def test_valid_signature(self):
        from python.helpers.webhook_verify import verify_github_signature

        secret = "test-secret"
        body = b'{"action":"opened"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_github_signature(body, sig, secret) is True

    def test_invalid_signature(self):
        from python.helpers.webhook_verify import verify_github_signature

        assert verify_github_signature(b"body", "sha256=bad", "secret") is False

    def test_missing_signature(self):
        from python.helpers.webhook_verify import verify_github_signature

        assert verify_github_signature(b"body", None, "secret") is False

    def test_wrong_prefix(self):
        from python.helpers.webhook_verify import verify_github_signature

        assert verify_github_signature(b"body", "sha1=abc", "secret") is False


class TestSlackSignature:
    def test_valid_signature(self):
        from python.helpers.webhook_verify import verify_slack_signature

        secret = "8f742231b10e8888abcd99yez67543"
        timestamp = str(int(time.time()))
        body = b"token=xyzz0WbapA4vBCDEFasx0q6G&team_id=T1DC2JH3J"
        sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
        sig = (
            "v0="
            + hmac.new(secret.encode(), sig_basestring, hashlib.sha256).hexdigest()
        )
        assert verify_slack_signature(body, sig, timestamp, secret) is True

    def test_invalid_signature(self):
        from python.helpers.webhook_verify import verify_slack_signature

        assert verify_slack_signature(b"body", "v0=bad", "123", "secret") is False

    def test_stale_timestamp(self):
        from python.helpers.webhook_verify import verify_slack_signature

        old_ts = str(int(time.time()) - 600)  # 10 minutes old
        assert verify_slack_signature(b"body", "v0=sig", old_ts, "secret") is False

    def test_missing_params(self):
        from python.helpers.webhook_verify import verify_slack_signature

        assert verify_slack_signature(b"body", None, None, "secret") is False


class TestJiraSignature:
    def test_valid_shared_secret(self):
        from python.helpers.webhook_verify import verify_jira_signature

        secret = "my-jira-secret"
        assert verify_jira_signature(secret, secret) is True

    def test_invalid_shared_secret(self):
        from python.helpers.webhook_verify import verify_jira_signature

        assert verify_jira_signature("provided", "expected") is False

    def test_missing_secret(self):
        from python.helpers.webhook_verify import verify_jira_signature

        assert verify_jira_signature(None, "expected") is False
