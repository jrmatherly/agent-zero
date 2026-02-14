# Jira Webhook Setup Guide

This guide walks through configuring Jira Cloud webhooks to send events to the Apollos AI platform integration.

## Prerequisites

- Jira Cloud project admin access
- A publicly accessible Apollos AI instance (or a tunnel like ngrok for development)

## Step 1: Generate a Shared Secret

Jira Cloud webhooks use a shared secret passed as a query parameter for authentication. Generate a strong random secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save this value — you'll use it in both Jira and Apollos AI configuration.

## Step 2: Create the Webhook in Jira

1. Go to **Jira Settings** (gear icon) > **System** > **WebHooks**.
   - Direct URL: `https://<your-site>.atlassian.net/plugins/servlet/webhooks`
2. Click **Create a WebHook**.
3. Fill in:
   - **Name**: e.g., "Apollos AI Agent"
   - **URL**: `https://<your-domain>/webhook_jira?secret=<your-shared-secret>`
   - **Status**: Active
4. Under **Events**, select:

   | Event | Purpose |
   |-------|---------|
   | Issue > created | New issue triggers agent processing |
   | Issue > updated | Label changes (e.g., adding "apollos-ai") trigger processing |
   | Comment > created | New comments trigger agent response |

5. Optionally, use the **JQL filter** to scope to specific projects:
   ```
   project = MYPROJECT
   ```
6. Click **Create**.

## Step 3: Configure Environment Variables

Add these to your `usr/.env` file (or set via environment):

```bash
# Shared secret (must match the ?secret= parameter in the webhook URL)
A0_SET_JIRA_WEBHOOK_SECRET=your-shared-secret-here

# Jira site URL (for API callbacks)
A0_SET_JIRA_SITE_URL=https://your-org.atlassian.net
```

Alternatively, configure via the UI under **Settings > Integrations**.

## Step 4: Enable Integrations

Set the master integration toggle:

```bash
A0_SET_INTEGRATIONS_ENABLED=true
```

## How It Works

1. When a matching event occurs in Jira, it sends a POST to `/webhook_jira?secret=...`.
2. The webhook handler verifies the shared secret matches the configured value.
3. For `jira:issue_updated` events, only label changes are processed (to support label-based triggering).
4. An `IntegrationMessage` is created with the issue context (key, summary, description, priority, status).
5. The `monologue_end` extension delivers the agent's response as a Jira comment, converting Markdown to Jira wiki markup.

## Supported Events

| Event | Trigger | Agent Action |
|-------|---------|-------------|
| `jira:issue_created` | New issue created | Analyze and respond |
| `jira:issue_updated` | Label added (e.g., "apollos-ai") | Process based on label trigger |
| `comment_created` | New comment on an issue | Respond to the comment |

## Jira Markup Conversion

The callback extension automatically converts the agent's Markdown response to Jira wiki markup:

| Markdown | Jira Markup |
|----------|-------------|
| `**bold**` | `*bold*` |
| `*italic*` | `_italic_` |
| `` `code` `` | `{{code}}` |
| `` ```lang\ncode\n``` `` | `{code:lang}\ncode\n{code}` |
| `# Heading` | `h1. Heading` |
| `- item` | `* item` |
| `1. item` | `# item` |
| `[text](url)` | `[text\|url]` |

## Development/Testing

For local development, use a tunnel:

```bash
# Using ngrok
ngrok http 5000

# Webhook URL: https://<ngrok-id>.ngrok.io/webhook_jira?secret=<your-secret>
```

You can re-trigger events by making changes in Jira (create an issue, add a comment, toggle a label).

## Troubleshooting

- **403 Invalid signature**: Verify the `?secret=` parameter in the Jira webhook URL matches `A0_SET_JIRA_WEBHOOK_SECRET`.
- **Events not arriving**: Check the webhook status in Jira Settings > WebHooks. Jira shows delivery logs with HTTP status codes.
- **Label-based triggers not working**: Only `jira:issue_updated` events with a changelog containing a `labels` field change are processed.
- **No agent response**: Ensure `A0_SET_INTEGRATIONS_ENABLED=true` and check the application logs.
