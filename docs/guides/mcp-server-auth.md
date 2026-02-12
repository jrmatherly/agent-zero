# MCP Server OAuth Authentication

This guide explains how to secure inbound MCP connections with Microsoft Entra ID OAuth, allowing IDE clients (VS Code, Cursor, Claude Code) to authenticate with Bearer tokens.

## Overview

Apollos AI exposes an MCP server at `/mcp` that IDE clients can connect to. By default, access is controlled via a shared **token-in-path** mechanism (the MCP server token from Settings). Phase 5 adds optional **OAuth Bearer token** authentication via Entra ID, enabling per-user identity and RBAC enforcement for MCP requests.

Both authentication methods coexist — enabling OAuth does not break token-in-path access.

## Prerequisites

- Apollos AI with Phase 5 auth system (Phases 0–4 complete)
- A Microsoft Entra ID tenant
- Azure Portal admin access to create App Registrations

## Azure App Registration

Create a **separate** App Registration for the MCP server (don't reuse the OIDC SSO app). For the complete Azure Portal walkthrough covering both the Web UI SSO and MCP API registrations, see [Azure Enterprise Setup](azure-enterprise-setup.md).

### 1. Register the app

1. Go to **Azure Portal** > **App registrations** > **New registration**
2. Name: `Apollos AI MCP API` (or similar)
3. Supported account types: Choose based on your needs
   - **Single tenant** for internal use
   - **Multitenant** if external clients need access
4. Redirect URI: Leave blank for now (clients provide their own)
5. Click **Register**

### 2. Expose an API

1. Go to **Expose an API**
2. Set **Application ID URI**: Accept the default (`api://{client-id}`) or set a custom one
3. **Add scopes** (these must match the server config):
   - `discover` — List available tools
   - `tools.read` — Read tool metadata
   - `tools.execute` — Execute tools
   - `chat` — Send and manage chat messages

### 3. Create a client secret

1. Go to **Certificates & secrets** > **New client secret**
2. Copy the secret value immediately (it won't be shown again)

### 4. Authorize client apps (optional)

FastMCP's `AzureProvider` uses an **OAuth proxy pattern** that handles [Dynamic Client Registration (DCR)](https://datatracker.ietf.org/doc/html/rfc7591) on behalf of MCP clients. This means most clients (Claude Code, Cursor, Windsurf) register dynamically through the proxy and do **not** need to be pre-authorized in Azure.

Pre-authorization is only needed if you want to skip user consent prompts or if you bypass the proxy and use direct Entra ID authentication (e.g., via Azure App Service Authentication).

To pre-authorize a client:

1. Go to **Expose an API** > **Add a client application**
2. Enter the client's Application ID (see table below)
3. Check all four scopes

#### Known client Application IDs

| Client | Application ID | Auth method |
|--------|---------------|-------------|
| VS Code (GitHub Copilot) | `aebc6443-996d-45c2-90f0-388ff96faa56` | Pre-registered |
| Claude Code | — | DCR via OAuth proxy |
| Cursor | — | DCR via OAuth proxy |
| Windsurf | — | DCR via OAuth proxy |
| Antigravity (Google) | — | Not supported (no MCP OAuth as of Feb 2026) |

Clients marked "DCR via OAuth proxy" register dynamically through the AzureProvider proxy — no pre-authorization needed. Only VS Code uses a fixed Application ID that can be pre-authorized in Entra ID.

## Server Configuration

Add these environment variables to `usr/.env` (see [Environment Variables Reference](../reference/environment-variables.md#mcp-server-oauth-inbound-auth) for full details):

```bash
# Required — enables MCP OAuth
MCP_AZURE_CLIENT_ID=<app-registration-client-id>
MCP_AZURE_CLIENT_SECRET=<client-secret-value>
MCP_AZURE_TENANT_ID=<your-tenant-guid>

# Required for production
MCP_SERVER_BASE_URL=https://your-domain.com
# Without jwt_signing_key, OAuth proxy tokens use ephemeral keys and won't survive server restarts
MCP_AZURE_JWT_SIGNING_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")

# Optional — only set if you changed the Application ID URI from Azure's default
# MCP_AZURE_IDENTIFIER_URI=api://<client-id>

# Optional — server-side restriction on client redirect URIs (not an Azure Portal setting).
# When unset, any redirect URI is accepted. DCR clients use http://localhost:{random-port}.
# MCP_AZURE_REDIRECT_URIS=http://localhost:*/callback
```

Restart the server. You should see:

```text
[MCP] Azure OAuth auth configured via AzureProvider
```

## How It Works

### Dual authentication

| Method | Endpoint | Use case |
|--------|----------|----------|
| Token-in-path | `/mcp/t-{token}/http` | Simple API access, legacy clients |
| OAuth Bearer | `/mcp/http` | IDE clients, per-user identity |

### OAuth flow

1. Client connects to `/mcp/http`
2. Server returns 401 with `WWW-Authenticate` header containing the resource metadata URL (RFC 9728)
3. Client fetches Protected Resource Metadata to discover the authorization server
4. Client initiates OAuth 2.1 authorization code flow with PKCE via Entra ID
5. User authenticates in browser and grants requested scopes
6. Client receives access token with granted scopes
7. Client sends requests with `Authorization: Bearer {token}`
8. Server validates JWT via JWKS (auto-fetched from Entra ID), enforces scopes, and resolves user identity

### Per-tool scope enforcement

Tools require the `chat` scope. Without it, tool invocations are denied:

```text
send_message  → requires "chat" scope
finish_chat   → requires "chat" scope
```

### RBAC enforcement

If the authenticated user exists in the auth database, Casbin RBAC is checked to verify MCP execute permissions within the user's org/team domain. The user must have org/team memberships for RBAC to pass — SSO users are auto-assigned to the default org/team by default (controlled by `A0_SET_SSO_AUTO_ASSIGN`). See [SSO Auto-Assignment](../reference/environment-variables.md#sso-auto-assignment) and [EntraID Group-Based Role Assignment](../reference/environment-variables.md#entraid-group-based-role-assignment) for details.

## IDE Client Configuration

### Claude Code

Add the MCP server via CLI:

```bash
claude mcp add apollos-ai --transport http https://your-domain.com/mcp/http
```

Claude Code automatically detects OAuth requirements via Protected Resource Metadata (RFC 9728) and initiates the browser-based authentication flow on first connection.

### VS Code (Copilot MCP)

In `.vscode/settings.json` or user settings:

```json
{
  "mcp": {
    "servers": {
      "apollos-ai": {
        "type": "http",
        "url": "https://your-domain.com/mcp/http"
      }
    }
  }
}
```

VS Code handles OAuth automatically when the server requires authentication.

### Cursor

In `.cursor/mcp.json` (global) or `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "apollos-ai": {
      "url": "https://your-domain.com/mcp/http",
      "transport": "streamable-http"
    }
  }
}
```

Cursor supports OAuth via DCR and will prompt for browser authentication on first connection.

### Windsurf

In `~/.windsurf/mcp.json` (global) or via **Settings > Tools & Integrations > New MCP Server**:

```json
{
  "mcpServers": {
    "apollos-ai": {
      "serverUrl": "https://your-domain.com/mcp/http",
      "transport": "streamable-http"
    }
  }
}
```

Windsurf supports OAuth for Streamable HTTP and SSE transports.

### Antigravity (Google)

As of February 2026, Antigravity does not support the MCP OAuth specification. It cannot authenticate with custom MCP servers using OAuth client credentials. Only Google-hosted and Google Cloud MCP servers are supported.

## Security Features

### Rate limiting

OAuth-authenticated MCP requests are rate-limited to 100 requests/minute per user.

### Audit logging

All MCP tool invocations are logged to the `audit_log` table with:
- User ID (from token claims)
- Action (`mcp_tool_invoke`)
- Resource (tool name)
- Details (chat ID, project)

### Login brute force protection

Local login attempts are protected with:
- Progressive delays (0, 1, 2, 4, 8 seconds)
- Account lockout after 5 failed attempts (5-minute cooldown)

## Troubleshooting

### "MCP forbidden" error

- Verify MCP server is enabled in Settings
- Check that the token-in-path is correct (for token-in-path mode)
- Verify OAuth env vars are set (for Bearer mode)

### OAuth flow not starting

- Verify `MCP_AZURE_CLIENT_ID`, `MCP_AZURE_CLIENT_SECRET`, `MCP_AZURE_TENANT_ID` are all set
- Check that `MCP_SERVER_BASE_URL` matches your actual server URL
- Verify the Azure App Registration has the correct scopes exposed

### Token rejected

- Verify the tenant ID is a specific GUID (not "common")
- Check that the client app is authorized in "Expose an API"
- Verify the user exists in the auth database (for RBAC)
- Check that the user has org/team memberships (for Casbin RBAC)

### User authenticated but gets 403

- The user exists but has no org/team memberships — Casbin denies all access
- Fix: Enable auto-assignment (`A0_SET_SSO_AUTO_ASSIGN=true`) or configure [group mappings](../reference/environment-variables.md#entraid-group-based-role-assignment)

For a comprehensive list of Azure-related errors and fixes, see the [Common Errors](azure-enterprise-setup.md#common-errors) table in the Azure Enterprise Setup guide.

---

## Related Documentation

- [Azure Enterprise Setup](azure-enterprise-setup.md) — Full Azure Portal configuration for both SSO and MCP app registrations, including verification checklist, troubleshooting, and production hardening
- [Environment Variables Reference](../reference/environment-variables.md) — Complete catalog of all environment variables including MCP OAuth, SSO auto-assignment, and group-based role assignment
