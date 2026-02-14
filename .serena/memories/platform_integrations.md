# Platform Integrations Architecture

## Overview
Inbound webhook receivers for Slack, GitHub, and Jira. Events are verified, parsed into IntegrationMessage models, registered as callbacks, processed by the agent, and responses delivered back to the originating platform.

## Webhook Handlers (python/api/)
- `webhook_slack.py` — Slack Events API: app_mention, DM messages. Signing secret + timestamp replay check. Dedup cache (5min TTL). Bot message filtering.
- `webhook_slack_oauth.py` — Slack OAuth identity linking (GET endpoint). Links Slack user to internal auth account.
- `webhook_github.py` — GitHub App webhooks: issues (opened/labeled), issue_comment (created), pull_request (opened/review_requested), PR review comments. HMAC-SHA256 signature verification.
- `webhook_jira.py` — Jira Cloud webhooks: jira:issue_created, jira:issue_updated (label changes only), comment_created. Shared secret via `?secret=` query parameter.

## Core Models (python/helpers/integration_models.py)
- `SourceType(StrEnum)` — SLACK, GITHUB, JIRA
- `IntegrationMessage(BaseModel)` — source, text, external_user_id/name, channel_id, thread_id, metadata
- `WebhookContext(BaseModel)` — source, channel_id, thread_id, team_id, metadata
- `CallbackRegistration(BaseModel)` — conversation_id, webhook_context, status, attempts, last_error, created_at
- `CallbackStatus(StrEnum)` — PENDING, PROCESSING, COMPLETED, ERROR, AWAITING_APPROVAL

## Callback System
- `callback_registry.py` — Thread-safe singleton in-memory store (dict[str, CallbackRegistration]). Methods: register, get, update_status, remove, list_pending, list_awaiting_approval, list_all.
- `_80_integration_callback.py` (monologue_end extension) — Fires after agent completes. Routes responses to platform-specific delivery (Slack chat.postMessage, GitHub issue comment, Jira comment). Skips AWAITING_APPROVAL status.
- `callback_retry.py` — Exponential backoff (2^attempt, capped at 300s). MAX_RETRY_ATTEMPTS=3. Resets status to PENDING for re-delivery.
- `callback_admin.py` — POST API with list/retry actions for managing failed callbacks (dead letter queue).

## Verification (python/helpers/webhook_verify.py)
- `verify_slack_signature(body, signature, timestamp, secret)` — HMAC-SHA256 with v0:timestamp:body format. 5-minute replay window.
- `verify_github_signature(body, signature, secret)` — HMAC-SHA256 with sha256= prefix.
- `verify_jira_signature(provided, expected)` — Simple string comparison of shared secret.

## Supporting Components
- `webhook_event_log.py` — Bounded deque (maxlen=1000) for audit logging. Singleton. Methods: record(), recent(limit, source).
- `webhook_events_get.py` — GET API: returns recent events with optional source filter.
- `integration_settings_get.py` — GET API: returns masked integration config (has_slack_secret, has_github_secret, etc.).
- `jira_markup.py` — Markdown-to-Jira wiki markup converter (bold, italic, code, headings, lists, links, code blocks).

## Settings (in Settings TypedDict)
All overridable via `A0_SET_*` environment variables:
- `integrations_enabled` (bool, default False) — Master toggle
- `slack_signing_secret` (str) — Slack App signing secret
- `slack_bot_token` (str) — Slack Bot OAuth Token (xoxb-...)
- `github_webhook_secret` (str) — GitHub App webhook secret
- `github_app_id` (str) — GitHub App ID
- `jira_webhook_secret` (str) — Jira shared secret
- `jira_site_url` (str) — Jira Cloud site URL

## WebUI
- `webui/components/settings/integrations/integrations-settings.html` — Integrations tab in Settings with platform credential forms.
- Settings tab added to `webui/components/settings/settings.html`

## Documentation
- `docs/integrations/README.md` — Architecture overview
- `docs/integrations/slack-bot-setup.md` — Slack Bot/App setup guide
- `docs/integrations/github-app-setup.md` — GitHub App setup guide
- `docs/integrations/jira-webhook-setup.md` — Jira webhook setup guide

## Tests (20 test files, ~130 tests)
Coverage across all webhook handlers, verification, callback system, retry logic, event logging, settings API, Jira markup, and identity linking.
