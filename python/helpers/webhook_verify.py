"""Webhook signature verification for external platforms.

Each platform uses a different signing mechanism:
- GitHub: HMAC-SHA256 of body with webhook secret, prefixed "sha256="
- Slack: HMAC-SHA256 of "v0:{timestamp}:{body}" with signing secret, prefixed "v0="
- Jira: Shared secret comparison (Jira Cloud webhook authentication)
"""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_github_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    Args:
        body: Raw request body bytes.
        signature: X-Hub-Signature-256 header value (e.g. "sha256=abc...").
        secret: Webhook secret configured in GitHub App.
    """
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def verify_slack_signature(
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    secret: str,
    *,
    max_age_seconds: int = 300,
) -> bool:
    """Verify Slack request signing secret.

    Args:
        body: Raw request body bytes.
        signature: X-Slack-Signature header value (e.g. "v0=abc...").
        timestamp: X-Slack-Request-Timestamp header value.
        secret: Slack app signing secret.
        max_age_seconds: Maximum age of request (default 5 minutes).
    """
    if not signature or not timestamp:
        return False
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(time.time() - ts) > max_age_seconds:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode()}".encode()
    expected = (
        "v0=" + hmac.new(secret.encode(), sig_basestring, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(signature, expected)


def verify_jira_signature(provided_secret: str | None, expected_secret: str) -> bool:
    """Verify Jira Cloud webhook shared secret.

    Jira Cloud webhooks include a shared secret in the request
    (via query parameter or header) that must match the configured value.

    Args:
        provided_secret: Secret from the incoming request.
        expected_secret: Secret configured when the webhook was registered.
    """
    if not provided_secret:
        return False
    return hmac.compare_digest(provided_secret, expected_secret)
