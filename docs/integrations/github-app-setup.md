# GitHub App Setup Guide

This guide walks through creating and configuring a GitHub App to receive webhooks for the Apollos AI platform integration.

## Prerequisites

- A GitHub account with organization admin access (or personal account)
- A publicly accessible Apollos AI instance (or a tunnel like ngrok for development)

## Step 1: Create a GitHub App

1. Go to **Settings > Developer settings > GitHub Apps > New GitHub App**
   - Organization: `https://github.com/organizations/<org>/settings/apps/new`
   - Personal: `https://github.com/settings/apps/new`

2. Fill in the required fields:
   - **GitHub App name**: e.g., "Apollos AI Agent"
   - **Homepage URL**: Your Apollos AI instance URL
   - **Webhook URL**: `https://<your-domain>/webhook_github`
   - **Webhook secret**: Generate a strong random secret (save this for Step 3)

3. Set **Permissions**:

   | Permission | Access | Purpose |
   |-----------|--------|---------|
   | Issues | Read & Write | Read issues, post comments |
   | Pull requests | Read & Write | Read PRs, post review comments |
   | Contents | Read & Write | Read/push code changes |
   | Metadata | Read-only | Required for all apps |

4. Subscribe to **Events**:
   - Issues
   - Issue comment
   - Pull request
   - Pull request review comment

5. Set **Where can this GitHub App be installed?** to "Only on this account" (or "Any account" for broader use).

6. Click **Create GitHub App**.

## Step 2: Install the App

1. After creation, click **Install App** in the left sidebar.
2. Choose the account/organization to install on.
3. Select repositories: **All repositories** or specific ones.
4. Click **Install**.

## Step 3: Configure Environment Variables

Add these to your `usr/.env` file (or set via environment):

```bash
# GitHub webhook secret (from Step 1)
A0_SET_GITHUB_WEBHOOK_SECRET=your-webhook-secret-here

# GitHub App ID (shown on the app settings page)
A0_SET_GITHUB_APP_ID=123456
```

Alternatively, configure via the UI under **Settings > Integrations**.

## Step 4: Enable Integrations

Set the master integration toggle:

```bash
A0_SET_INTEGRATIONS_ENABLED=true
```

## How It Works

1. When an issue is opened/labeled or a comment mentions the bot, GitHub sends a webhook to `/webhook_github`.
2. The webhook handler verifies the signature, extracts the event context, and creates an agent conversation.
3. The agent processes the request using the GitHub context prompt template.
4. When the agent completes, the callback extension posts the result as a comment on the originating issue or PR.

## Supported Events

| Event | Trigger | Agent Action |
|-------|---------|-------------|
| Issue opened | New issue created | Analyze and respond |
| Issue labeled | Label added (e.g., "apollos-ai") | Process based on label |
| Issue comment | Comment with @mention | Respond to request |
| PR opened | New pull request | Review and comment |
| PR review requested | Review requested | Perform code review |
| PR review comment | Comment on PR diff | Respond in thread |

## Development/Testing

For local development, use a tunnel to expose your instance:

```bash
# Using ngrok
ngrok http 50080

# Then set webhook URL to: https://<ngrok-id>.ngrok.io/webhook_github
```

You can also use the GitHub webhook delivery log to replay events for debugging:
**App Settings > Advanced > Recent Deliveries**

## Troubleshooting

- **403 Invalid signature**: Verify `A0_SET_GITHUB_WEBHOOK_SECRET` matches the webhook secret in GitHub App settings.
- **Events not arriving**: Check that the app is installed on the repository and the correct events are subscribed.
- **No agent response**: Ensure `A0_SET_INTEGRATIONS_ENABLED=true` and check the application logs.
