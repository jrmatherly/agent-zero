# Platform Integrations

Apollos AI can receive events from external platforms via webhooks, process them through the agent loop, and deliver responses back to the originating platform.

## Supported Platforms

| Platform | Webhook Endpoint | Setup Guide |
|----------|-----------------|-------------|
| **Slack** | `POST /webhook_slack` | [Slack Bot Setup](slack-bot-setup.md) |
| **GitHub** | `POST /webhook_github` | [GitHub App Setup](github-app-setup.md) |
| **Jira** | `POST /webhook_jira` | [Jira Webhook Setup](jira-webhook-setup.md) |

## Architecture

```
Platform (Slack/GitHub/Jira)
    │
    ▼  webhook POST
┌──────────────────────┐
│  Webhook Handler     │  Verify signature → parse event → create IntegrationMessage
│  python/api/         │
└──────────┬───────────┘
           │ register callback
           ▼
┌──────────────────────┐
│  Callback Registry   │  In-memory store: conversation_id → CallbackRegistration
│  python/helpers/     │
└──────────┬───────────┘
           │ agent processes
           ▼
┌──────────────────────┐
│  Callback Extension  │  monologue_end hook delivers response to platform
│  python/extensions/  │
└──────────┬───────────┘
           │ API call
           ▼
    Platform (response posted)
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| Integration models | `python/helpers/integration_models.py` | Pydantic models: `SourceType`, `IntegrationMessage`, `WebhookContext`, `CallbackRegistration`, `CallbackStatus` |
| Webhook verification | `python/helpers/webhook_verify.py` | Platform-specific signature verification (HMAC-SHA256 for Slack/GitHub, shared secret for Jira) |
| Callback registry | `python/helpers/callback_registry.py` | Thread-safe singleton in-memory store for pending callbacks |
| Callback extension | `python/extensions/monologue_end/_80_integration_callback.py` | Lifecycle hook that delivers agent responses back to platforms |
| Callback retry | `python/helpers/callback_retry.py` | Exponential backoff retry for failed deliveries |
| Callback admin API | `python/api/callback_admin.py` | List/retry failed callbacks |
| Webhook event log | `python/helpers/webhook_event_log.py` | Bounded in-memory audit log of recent inbound events |
| Event log API | `python/api/webhook_events_get.py` | Query recent webhook events |
| Settings API | `python/api/integration_settings_get.py` | Read integration config (secrets masked) |

### Settings UI

Configure all platform credentials via **Settings > Integrations** in the web UI, or use `A0_SET_*` environment variables. See [Environment Variables Reference](../reference/environment-variables.md#platform-integrations).

## Enabling Integrations

1. Set the master toggle: `A0_SET_INTEGRATIONS_ENABLED=true` (or toggle in Settings UI)
2. Configure at least one platform following its setup guide
3. Ensure your instance is reachable by the platform's webhook delivery (use a tunnel like ngrok for development)

## Monitoring

- **Webhook event log**: `GET /webhook_events_get?limit=50&source=github` — recent inbound events
- **Callback admin**: `POST /callback_admin` with `{"action": "list"}` — pending/failed callback status
- **Application logs**: Webhook events are logged with `PrintStyle(font_color="cyan")`
