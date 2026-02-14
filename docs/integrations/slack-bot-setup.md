# Slack Bot Setup Guide

This guide walks through creating and configuring a Slack App to receive events for the Apollos AI platform integration.

## Prerequisites

- A Slack workspace where you have admin permissions
- A publicly accessible Apollos AI instance (or a tunnel like ngrok for development)

## Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**.
2. Choose **From scratch**.
3. Enter a name (e.g., "Apollos AI") and select your workspace.
4. Click **Create App**.

## Step 2: Configure OAuth & Permissions

1. In the left sidebar, go to **OAuth & Permissions**.
2. Under **Bot Token Scopes**, add:

   | Scope | Purpose |
   |-------|---------|
   | `app_mentions:read` | Receive @mention events |
   | `chat:write` | Post responses to channels |
   | `im:history` | Read direct messages |
   | `im:read` | Access DM channel info |
   | `im:write` | Send direct messages |

3. Click **Install to Workspace** and authorize the app.
4. Copy the **Bot User OAuth Token** (`xoxb-...`) — you'll need this in Step 4.

## Step 3: Enable Events API

1. In the left sidebar, go to **Event Subscriptions**.
2. Toggle **Enable Events** to On.
3. Set **Request URL** to: `https://<your-domain>/webhook_slack`
   - Slack will send a verification challenge; the webhook handler responds automatically.
4. Under **Subscribe to bot events**, add:

   | Event | Trigger |
   |-------|---------|
   | `app_mention` | Someone @mentions your bot in a channel |
   | `message.im` | Someone sends a direct message to your bot |

5. Click **Save Changes**.

## Step 4: Configure Environment Variables

Add these to your `usr/.env` file (or set via environment):

```bash
# Slack signing secret (from App Settings > Basic Information > Signing Secret)
A0_SET_SLACK_SIGNING_SECRET=your-signing-secret-here

# Bot User OAuth Token (from Step 2)
A0_SET_SLACK_BOT_TOKEN=xoxb-your-bot-token-here
```

Alternatively, configure via the UI under **Settings > Integrations**.

## Step 5: Enable Integrations

Set the master integration toggle:

```bash
A0_SET_INTEGRATIONS_ENABLED=true
```

## How It Works

1. When a user @mentions the bot or sends a DM, Slack sends an `event_callback` to `/webhook_slack`.
2. The webhook handler verifies the request signature using the signing secret and a timing-based replay attack check.
3. Duplicate events are filtered using an in-memory dedup cache (5-minute TTL).
4. Bot messages are ignored to prevent response loops.
5. An `IntegrationMessage` is created and a callback is registered for when the agent completes.
6. The `monologue_end` extension delivers the agent's response back to the Slack channel/thread.

## Supported Events

| Event | Trigger | Agent Action |
|-------|---------|-------------|
| `app_mention` | @mention in any channel the bot is in | Respond in thread |
| `message.im` | Direct message to the bot | Respond in DM |

## Identity Linking (Optional)

Users can link their Slack identity to their Apollos AI account via OAuth:

1. The user clicks "Connect Slack" in the UI.
2. They are redirected to Slack's OAuth consent screen.
3. After approval, `/webhook_slack_oauth` exchanges the code for tokens and links the identities.

This enables the agent to personalize responses based on the user's internal account context.

## Development/Testing

For local development, use a tunnel to expose your instance:

```bash
# Using ngrok
ngrok http 5000

# Then set Request URL to: https://<ngrok-id>.ngrok.io/webhook_slack
```

You can also use the Slack Events API debugger in your app settings.

## Troubleshooting

- **403 Invalid signature**: Verify `A0_SET_SLACK_SIGNING_SECRET` matches the Signing Secret in your Slack App's Basic Information page.
- **URL verification failing**: Ensure the webhook endpoint is reachable and returns `{"challenge": "..."}` for `url_verification` requests.
- **Bot not responding**: Check that the bot is invited to the channel, `A0_SET_INTEGRATIONS_ENABLED=true`, and the bot token has the required scopes.
- **Duplicate responses**: The handler includes dedup logic, but verify you haven't subscribed to overlapping event types.
