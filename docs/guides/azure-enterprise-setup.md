# Azure Enterprise Application Configuration

Complete Azure EntraID configuration guide for Apollos AI SSO and MCP OAuth authentication.

**Audience:** Administrators configuring the Azure side of the integration

---

## Architecture Overview

Apollos AI requires **two separate** Azure app registrations:

| Registration | Purpose | Auth Flow | Env Prefix | Account Type |
|-------------|---------|-----------|------------|-------------|
| **Apollos AI** | Web UI SSO | Authorization Code (MSAL) | `OIDC_*` | Single tenant |
| **Apollos AI MCP API** | MCP server inbound auth | OAuth 2.0 Bearer (FastMCP AzureProvider) | `MCP_AZURE_*` | Single or Multi tenant |

**Why two registrations?** The Web UI SSO app is a confidential client (server-side MSAL with user-facing login). The MCP API app is a resource server that exposes custom API scopes and uses an OAuth proxy pattern for Dynamic Client Registration (DCR). These are fundamentally different OAuth roles with different security boundaries — mixing them creates scope confusion and complicates token validation. See [MCP Server Auth](mcp-server-auth.md) for additional context.

---

## Part 1: Web UI SSO App Registration

### Step 1: Create the App Registration

1. Navigate to **Azure Portal** > **Microsoft Entra ID** > **App registrations** > **New registration**
2. Configure:

| Field | Value |
|-------|-------|
| **Name** | `Apollos AI` (or your preferred display name) |
| **Supported account types** | `Accounts in this organizational directory only` (Single tenant) |
| **Redirect URI (Web)** | `http://localhost:5000/auth/callback` |

3. Click **Register**
4. Note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page

### Step 2: Add Redirect URIs

Navigate to **Authentication** > **Platform configurations** > **Web** > **Add URI**

Add the SSO callback URLs (**Web UI only** — MCP OAuth uses a separate registration):

```text
http://localhost:5000/auth/callback          <- Local development
https://your-domain.com/auth/callback        <- Production
```

> **Important:** Every URL must be registered here or Azure will reject the redirect with `AADSTS50011: The redirect URI specified in the request does not match`.
>
> **Do NOT add MCP OAuth callback URLs here** — those belong on the separate MCP API registration. See Part 4.

### Step 3: Configure Authentication Settings

Still on the **Authentication** page:

| Setting | Value | Why |
|---------|-------|-----|
| **Front-channel logout URL** | *(leave blank)* | Optional — set if you need single-logout |
| **Implicit grant and hybrid flows** | Unchecked: Access tokens, ID tokens | **Leave unchecked** — we use auth code flow, not implicit |
| **Allow public client flows** | No | We are a confidential client (server-side) |

### Step 4: Create Client Secret

Navigate to **Certificates & secrets** > **Client secrets** > **New client secret**

| Field | Value |
|-------|-------|
| **Description** | `Apollos AI Production` (or `Dev`) |
| **Expires** | Choose based on your rotation policy (6 months, 12 months, or 24 months) |

**Copy the secret VALUE immediately** — it is only shown once. This becomes `OIDC_CLIENT_SECRET`. The MCP API app registration has its own separate secret (see Step 10).

> **Production tip:** Set a calendar reminder to rotate before expiration. Azure will not warn you — the app will just break.

---

## Part 2: API Permissions

### Step 5: Configure Microsoft Graph Permissions

Navigate to **API permissions** > **Add a permission** > **Microsoft Graph** > **Delegated permissions**

Add these permissions:

| Permission | Type | Purpose |
|-----------|------|---------|
| `openid` | Delegated | OIDC authentication (required) |
| `profile` | Delegated | User name and profile info |
| `email` | Delegated | User email address |
| `User.Read` | Delegated | Read user profile (explicitly requested by MSAL) |

> `User.Read` is already added by default when you create an app registration.

**If using group-based RBAC** (recommended for production), also add:

| Permission | Type | Purpose |
|-----------|------|---------|
| `GroupMember.Read.All` | Delegated | Fetch user's group memberships via Graph API (overage scenario) |

### Step 6: Grant Admin Consent

Click **Grant admin consent for [Your Tenant]** > **Yes**

This pre-approves the permissions for all users in your tenant. Without this, each user sees a consent prompt on first login.

> **Status check:** All permissions should show "Granted for [Tenant]" in green.

---

## Part 3: Token Configuration (Groups Claim)

This is **critical** for the RBAC group mapping feature (`sync_group_memberships()`).

### Step 7: Add Groups Claim to Tokens

Navigate to **Token configuration** > **Add groups claim**

| Setting | Value |
|---------|-------|
| **Select group types** | Security groups (checked) |
| **Customize token properties by type:** | |
| ID token: `Group ID` | Selected |
| Access token: `Group ID` | Selected |
| SAML: `Group ID` | Not needed |

Click **Add**

### How Groups Flow Through the System

```text
EntraID Token Claims                    Apollos AI
-----------------                       ----------
"groups": [
  "a1b2c3...",  ----------------------> sync_group_memberships()
  "d4e5f6..."   ---------------------->   looks up entra_group_mappings table
]                                         maps EntraID group IDs -> local org/team
                                          creates OrgMembership + TeamMembership

                                        sync_user_roles()
                                          reads memberships -> Casbin roles
                                          "member" -> can access resources
```

### Group Overage Handling

If a user belongs to **>200 groups** (common in large enterprises), Azure cannot fit all group IDs in the token. Instead, it includes a `_claim_names` field signaling overage. The app detects this and fetches groups via Microsoft Graph API:

```python
# python/helpers/auth.py:162-171
def _resolve_groups(self, claims, access_token):
    if "groups" in claims:
        return claims["groups"]                    # Normal: <200 groups
    if "_claim_names" in claims:
        return self._fetch_groups_from_graph(...)  # Overage: >200 groups
```

This requires the `GroupMember.Read.All` permission and a valid access token.

### Step 8: Configure Group Mappings in Apollos AI

After EntraID is configured, map EntraID security groups to local orgs/teams.

#### Option A: Environment Variable Bootstrap (Recommended)

For automated deployments, define group mappings in `usr/.env`. They are seeded automatically at every startup:

```bash
# Format: entra_group_id:org_slug:team_slug:role (semicolon-separated)
# Get group Object IDs from Azure Portal > Entra ID > Groups > [Group] > Object Id
A0_SET_SSO_GROUP_MAPPINGS="<ENTRA-GROUP-ID-1>:default:default:member;<ENTRA-GROUP-ID-2>:default:default:team_lead"
```

Mappings are idempotent — safe for repeated startup. See [Environment Variables](../reference/environment-variables.md#sso-group-mapping-bootstrap) for full format documentation and available roles.

#### Option B: Admin API (Manual)

For interactive configuration or managing mappings after initial deployment, use the admin API:

```bash
# 1. Get EntraID Group Object IDs from Azure Portal
#    Azure Portal > Entra ID > Groups > [Your Group] > Object Id

# 2. Get local org/team IDs via admin API
curl -X POST http://localhost:5000/admin_orgs \
  -H "Content-Type: application/json" \
  -b <admin-session-cookie> \
  -d '{"action": "list"}'

curl -X POST http://localhost:5000/admin_teams \
  -H "Content-Type: application/json" \
  -b <admin-session-cookie> \
  -d '{"action": "list", "org_id": "<ORG_ID>"}'

# 3. Create mappings via admin API (logged in as admin)
curl -X POST http://localhost:5000/admin_group_mappings \
  -H "Content-Type: application/json" \
  -b <admin-session-cookie> \
  -d '{
    "action": "upsert",
    "entra_group_id": "<ENTRA-SECURITY-GROUP-OBJECT-ID>",
    "org_id": "<LOCAL-ORG-ID>",
    "team_id": "<LOCAL-TEAM-ID>",
    "role": "member"
  }'
```

> **Without group mappings:** SSO users are auto-assigned to the default org/team as `member` by default (controlled by `A0_SET_SSO_AUTO_ASSIGN`). To require explicit group mappings instead, set `A0_SET_SSO_AUTO_ASSIGN=false` in `usr/.env`. See [Environment Variables](../reference/environment-variables.md#sso-auto-assignment) for details.

**Available roles for group mappings:**

| Role | Org-level Casbin Policy | Team-level Casbin Policy | Description |
|------|-------------------------|--------------------------|-------------|
| `owner` | `org_owner` | — | Full access to all org resources |
| `admin` | `org_admin` | — | Manage org settings, admin panel, MCP, knowledge |
| `lead` | — | `team_lead` | Full access within team scope |
| `member` | `member` | `member` | Standard access: create chats, read settings, upload knowledge |
| `viewer` | `viewer` | `viewer` | Read-only access |

---

## Part 4: MCP API App Registration (Separate)

This section covers the **second** app registration for the MCP server OAuth feature. This is a separate registration from the Web UI SSO app. Only needed if IDE clients (VS Code, Claude Code, Cursor, Windsurf) will authenticate via OAuth instead of token-in-path.

> **Reference:** [MCP Server Auth](mcp-server-auth.md) for full MCP auth documentation.

### Step 9: Create the MCP API App Registration

1. Navigate to **Azure Portal** > **Microsoft Entra ID** > **App registrations** > **New registration**
2. Configure:

| Field | Value |
|-------|-------|
| **Name** | `Apollos AI MCP API` |
| **Supported account types** | `Single tenant` (internal) or `Multitenant` (external IDE clients) |
| **Redirect URI** | Leave blank (clients provide their own via DCR) |

3. Click **Register**
4. Note the **Application (client) ID** and **Directory (tenant) ID**

### Step 10: Create Client Secret

Navigate to **Certificates & secrets** > **New client secret**

Copy the value immediately — this becomes `MCP_AZURE_CLIENT_SECRET`.

### Step 11: Define the Application ID URI

Navigate to **Expose an API** > **Set** the Application ID URI:

```text
api://<MCP-CLIENT-ID>
```

Accept the default or set a custom URI. This becomes `MCP_AZURE_IDENTIFIER_URI` (defaults to `api://{client_id}` if not set).

### Step 12: Add OAuth Scopes

Still on **Expose an API** > **Add a scope** for each MCP scope:

| Scope Name | Admin Consent Display | User Consent Display | Who Can Consent | State |
|-----------|----------------------|---------------------|----------------|-------|
| `discover` | Discover available MCP tools | Discover available MCP tools | Admins and users | Enabled |
| `tools.read` | Read MCP tool definitions | Read available tools | Admins and users | Enabled |
| `tools.execute` | Execute MCP tools | Run tools on your behalf | Admins and users | Enabled |
| `chat` | Chat with AI agents | Chat with AI agents | Admins and users | Enabled |

Each scope's full identifier will be: `api://<MCP-CLIENT-ID>/discover`, etc.

### Step 13: Authorize Client Applications (Optional)

FastMCP's `AzureProvider` uses an **OAuth proxy pattern** that handles Dynamic Client Registration (DCR) on behalf of MCP clients. Most clients (Claude Code, Cursor, Windsurf) register dynamically through the proxy and do **not** need pre-authorization.

Pre-authorization is only needed to skip user consent prompts or for clients with fixed Application IDs:

**Expose an API** > **Add a client application**

| Client | Application ID | Auth Method |
|--------|---------------|-------------|
| VS Code (GitHub Copilot) | `aebc6443-996d-45c2-90f0-388ff96faa56` | Pre-registered — can be pre-authorized |
| Claude Code | — | DCR via OAuth proxy — no pre-auth needed |
| Cursor | — | DCR via OAuth proxy — no pre-auth needed |
| Windsurf | — | DCR via OAuth proxy — no pre-auth needed |
| Antigravity (Google) | — | Not supported (no MCP OAuth as of Feb 2026) |

> **Note:** The MCP API registration does NOT need Microsoft Graph API permissions — it only serves as a resource server. The `User.Read`, `openid`, etc. permissions belong on the Web UI SSO registration only.

---

## Part 5: Enterprise Application Settings

Configure both enterprise applications in **Enterprise Applications**:

### Step 14: User Assignment

**Apollos AI (Web UI SSO):**

Navigate to **Enterprise Applications** > **Apollos AI** > **Properties**

| Setting | Development | Production |
|---------|-------------|------------|
| **Assignment required?** | `No` (any tenant user can sign in) | `Yes` (only assigned users/groups) |
| **Visible to users?** | `Yes` | `Yes` (appears in My Apps portal) |

**Apollos AI MCP API:**

Navigate to **Enterprise Applications** > **Apollos AI MCP API** > **Properties**

| Setting | Development | Production |
|---------|-------------|------------|
| **Assignment required?** | `No` | `Yes` (restrict which users can use IDE MCP access) |
| **Visible to users?** | `No` | `No` (API-only, not user-facing) |

If **Assignment required = Yes**, assign users or groups:

**Enterprise Applications** > **[App]** > **Users and groups** > **Add user/group**

> This is Azure-side access control, independent of Apollos AI's Casbin RBAC. A user must pass both: (1) Azure assignment check > (2) Apollos AI RBAC check.

### Step 15: Conditional Access (Production)

For production deployments, consider Conditional Access policies:

**Entra ID** > **Security** > **Conditional Access** > **New policy**

| Policy | Setting |
|--------|---------|
| **Require MFA** | Target: Apollos AI app, Grant: Require MFA |
| **Block external access** | Target: Apollos AI app, Conditions: Locations (exclude trusted), Grant: Block |
| **Require compliant device** | Target: Apollos AI app, Grant: Require compliant device |
| **Session controls** | Sign-in frequency: 8 hours (matches `PERMANENT_SESSION_LIFETIME`) |

---

## Part 6: Environment Variables

See [Environment Variables Reference](../reference/environment-variables.md) for the complete catalog.

### Web UI SSO — Registration #1 (`usr/.env`)

```bash
# Required — EntraID OIDC SSO (from "Apollos AI" app registration)
OIDC_TENANT_ID=<TENANT-UUID>
OIDC_CLIENT_ID=<WEB-UI-SSO-CLIENT-ID>
OIDC_CLIENT_SECRET=<WEB-UI-SSO-CLIENT-SECRET>

# Optional — explicit callback URL (auto-generated if unset)
# Set this in production behind a reverse proxy
OIDC_REDIRECT_URI=http://localhost:5000/auth/callback

# Required — encryption key for MSAL token cache + API key vault
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
VAULT_MASTER_KEY=<64-char-hex-string>

# Bootstrap admin (created on first launch)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<strong-password>
```

### SSO Auto-Assignment (`usr/.env`)

Controls automatic membership provisioning for SSO users without EntraID group mappings:

```bash
# Auto-assign SSO users to default org/team when they have no EntraID group mappings.
# Set to "false" in production to require explicit admin-managed group mappings.
A0_SET_SSO_AUTO_ASSIGN=true

# Default role for auto-assigned SSO users (member, viewer).
A0_SET_SSO_DEFAULT_ROLE=member
```

### MCP Server OAuth — Registration #2 (`usr/.env`) — Optional

These use a **different app registration** than the SSO variables above.

```bash
# Required for MCP OAuth (from "Apollos AI MCP API" app registration)
# These are DIFFERENT from the OIDC_* values — separate app registration
MCP_AZURE_CLIENT_ID=<MCP-API-CLIENT-ID>
MCP_AZURE_CLIENT_SECRET=<MCP-API-CLIENT-SECRET>
MCP_AZURE_TENANT_ID=<TENANT-UUID>

# Application ID URI (defaults to api://<MCP_AZURE_CLIENT_ID>)
MCP_AZURE_IDENTIFIER_URI=api://<MCP-API-CLIENT-ID>

# Public base URL of the MCP server (for OAuth metadata/callbacks)
MCP_SERVER_BASE_URL=http://localhost:50080

# Server-side restriction on client redirect URIs (comma-separated)
# When unset, any redirect URI is accepted. DCR clients use http://localhost:{random-port}
# MCP_AZURE_REDIRECT_URIS=http://localhost:*/callback

# Persistent JWT signing key for OAuth proxy token signing (REQUIRED for production)
# Without this, tokens use ephemeral keys and won't survive server restarts
# Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
MCP_AZURE_JWT_SIGNING_KEY=<url-safe-token-string>
```

### Session & Security (`usr/.env`)

```bash
# Flask session encryption key (auto-generated if unset, but ephemeral across restarts)
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=<64-char-hex-string>
```

> **Production requirement:** Set `FLASK_SECRET_KEY` explicitly. Without it, a random key is generated each time the server starts, which invalidates all existing sessions (users get logged out on every restart).

---

## Part 7: Verification & Troubleshooting

### Verification Checklist

**Web UI SSO (Registration #1):**

| # | Check | How |
|---|-------|-----|
| 1 | App registration exists | Azure Portal > App registrations > Apollos AI |
| 2 | Client ID matches env | Compare Overview > Application (client) ID with `OIDC_CLIENT_ID` |
| 3 | Tenant ID matches env | Compare Overview > Directory (tenant) ID with `OIDC_TENANT_ID` |
| 4 | Secret is valid | Certificates & secrets > verify expiration date |
| 5 | Redirect URI registered | Authentication > `http://localhost:5000/auth/callback` listed |
| 6 | Graph permissions granted | API permissions > all show green "Granted" |
| 7 | Groups claim configured | Token configuration > "groups" claim present |
| 8 | Group mappings exist | Admin API: `POST /admin_group_mappings {"action": "list"}` |
| 9 | Login works | Browse to `http://localhost:5000` > "Sign in with Microsoft" |
| 10 | User has memberships | Check server logs for "has no org memberships" warnings |

**MCP API (Registration #2):**

| # | Check | How |
|---|-------|-----|
| 11 | Separate app registration exists | Azure Portal > App registrations > Apollos AI MCP API |
| 12 | Client ID matches env | Compare with `MCP_AZURE_CLIENT_ID` (different from `OIDC_CLIENT_ID`) |
| 13 | Secret is valid | Certificates & secrets > verify expiration date |
| 14 | Application ID URI set | Expose an API > `api://<MCP-CLIENT-ID>` |
| 15 | 4 scopes defined | Expose an API > discover, tools.read, tools.execute, chat |
| 16 | Server starts with MCP auth | Look for `[MCP] Azure OAuth auth configured via AzureProvider` in logs |
| 17 | IDE client can connect | `claude mcp add apollos-ai --transport http http://localhost:50080/mcp/http` |

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `AADSTS50011: redirect URI does not match` | Callback URL not registered in Azure | Add URL to Authentication > Redirect URIs |
| `AADSTS7000218: request body must contain client_assertion or client_secret` | Missing or expired client secret | Create new secret > update `OIDC_CLIENT_SECRET` |
| `AADSTS700016: Application not found in directory` | Wrong tenant ID or app not in this tenant | Verify `OIDC_TENANT_ID` matches the directory |
| `AADSTS65001: user has not consented` | Admin consent not granted | API permissions > Grant admin consent |
| `OIDC authentication failed: invalid_grant` | Auth flow expired or replayed | Retry login — stale `auth_flow` in session |
| User sees 403 on all endpoints | No org/team memberships | Configure group mappings OR set `A0_SET_SSO_AUTO_ASSIGN=true` |
| `MSAL token cache corrupted` | `VAULT_MASTER_KEY` changed | Delete `usr/auth_token_cache.bin` and re-login |
| Groups not in token claims | Token configuration missing | Add groups claim in Token configuration |
| Groups empty despite config | User not in any security groups | Assign user to EntraID security groups |

### Useful Azure CLI Commands

```bash
# List app registrations in your tenant
az ad app list --display-name "Apollos AI" --query "[].{name:displayName, appId:appId}" -o table

# Check what permissions are configured
az ad app show --id <CLIENT_ID> --query "requiredResourceAccess"

# List user's group memberships
az ad user get-member-objects --id <USER-UPN> --security-enabled-only

# Check token claims (decode a JWT)
# Copy the access_token from browser DevTools > Network tab > auth/callback response
# Paste at https://jwt.ms to inspect claims
```

### Testing the Token Claims

To verify the ID token includes the expected claims:

1. Log in via the web UI
2. Open browser DevTools > Network tab
3. Find the `/auth/callback` request
4. The `code` parameter in the URL is the auth code (not directly useful)
5. Check server logs for the decoded claims (add temporary logging if needed)

Or decode the token at [jwt.ms](https://jwt.ms):

Expected claims in ID token:

```json
{
  "aud": "<CLIENT_ID>",
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "oid": "ab5ce79b-...",
  "preferred_username": "user@domain.com",
  "name": "First Last",
  "groups": ["a1b2c3...", "d4e5f6..."],
  "roles": ["Admin", "User"]
}
```

Claim-to-field mapping:

| Token Claim | Apollos AI Field | Usage |
|-------------|-----------------|-------|
| `oid` | `user.id` | Stable user identifier (Azure AD object ID) |
| `preferred_username` | `user.email` | Email address for display and lookup |
| `name` | `user.display_name` | Display name in UI |
| `groups` | `entra_group_mappings` lookup | Mapped to org/team memberships via admin-configured group mappings |
| `roles` | *(reserved)* | Optional app roles (not currently used by Apollos AI RBAC) |

---

## Part 8: Production Hardening

| Area | Development | Production |
|------|-------------|------------|
| **App registrations** | 2 (SSO + MCP API) | 2 (SSO + MCP API) — never share |
| **Redirect URIs** | `http://localhost:5000/*` | `https://your-domain.com/*` only |
| **Client secret expiration** | 24 months | 6 months with rotation automation |
| **Session cookie** | `Secure=False` (HTTP) | `SESSION_COOKIE_SECURE=True` (HTTPS only) |
| **Assignment required** | No | Yes — restrict to specific users/groups |
| **Conditional Access** | None | MFA + compliant device + trusted locations |
| **FLASK_SECRET_KEY** | Auto-generated | Explicit, stored in key vault |
| **VAULT_MASTER_KEY** | Generated once | Stored in Azure Key Vault or 1Password |
| **Group mappings** | Auto-assign default (`A0_SET_SSO_AUTO_ASSIGN=true`) | Explicit per-group mappings (`A0_SET_SSO_AUTO_ASSIGN=false`) |
| **Implicit grant** | Disabled | Disabled |
| **Public client** | Disabled | Disabled |

---

## Quick Reference: Full Auth Flow Sequence

```text
Browser                    Apollos AI (Flask)           Azure EntraID
-------                    ------------------           -------------
GET /login/entra -------->
                           get_login_url()
                           MSAL initiate_auth_code_flow()
                           Store flow in session
                <-------- 302 Redirect to Azure

GET /authorize -------------------------------------------->
                                                       User authenticates
                                                       (MFA if configured)
                                                       User consents
               <---------------------------------------- 302 + code + state

GET /auth/callback ------>
                           process_callback()
                           MSAL acquire_token_by_auth_code_flow()
                           Extract claims (oid, email, name, groups)
                           establish_session()
                             upsert_user() -> create/update DB record
                             sync_group_memberships() -> map groups -> orgs/teams
                             _auto_assign_default_memberships() -> fallback if no mappings
                             sync_user_roles() -> update Casbin policies
                             Populate Flask session
                <-------- 302 Redirect to /

GET / ----------------->
                           @requires_auth
                           Serve index.html
                <-------- 200 + Full UI

POST /projects ---------->
                           @requires_auth
                           RBAC: check_permission(user, domain, "projects", "read")
                             Casbin: user has "member" role
                             Policy: member + org:*/team:* + projects + read
                <-------- 200 + project data
```

---

## Related Documentation

- [MCP Server Auth](mcp-server-auth.md) — MCP OAuth Bearer token authentication, IDE client configuration, per-tool scope enforcement, and security features
- [Environment Variables Reference](../reference/environment-variables.md) — Complete catalog of all environment variables including OIDC SSO, MCP OAuth, SSO auto-assignment, and group-based role assignment
