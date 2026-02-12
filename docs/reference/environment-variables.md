# Environment Variables Reference

Apollos AI reads environment variables from two sources:

1. **`usr/.env`** — Project-local dotenv file (loaded at startup via `python-dotenv`)
2. **System environment** — Standard shell/container env vars

Variables in `usr/.env` override system environment. The file is gitignored and never committed.

---

## Authentication & Security

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `AUTH_LOGIN` | Legacy single-user login username. For multi-user accounts, use `ADMIN_EMAIL`/`ADMIN_PASSWORD` instead. Kept as a backward-compatible fallback. | Any string | *(empty)* | No |
| `AUTH_PASSWORD` | Legacy single-user login password. Paired with `AUTH_LOGIN`. | Any string | *(empty)* | No |
| `ROOT_PASSWORD` | Root password for code execution container. Auto-generated (32-char alphanumeric) inside Docker if unset. | Any string | *(auto-generated in Docker)* | No |
| `RFC_PASSWORD` | Remote Function Call password for SSH/HTTP to execution sandbox | Any string | *(empty)* | No |
| `FLASK_SECRET_KEY` | Flask session signing key; auto-generated if unset | Hex string (64 chars) | Random `secrets.token_hex(32)` | No |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins for CSRF validation | URL list | *(empty — auto-populated on first visit)* | No |

**Generating secure values:**

```bash
# ROOT_PASSWORD — 32-char alphanumeric (matches Docker auto-generation format)
python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"

# RFC_PASSWORD — URL-safe token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# FLASK_SECRET_KEY — 64-char hex string (matches app's secrets.token_hex(32) format)
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Multi-User Auth Database

The multi-user authentication system uses SQLAlchemy with an SQLite (or PostgreSQL) database to store users, organizations, teams, and API key vault entries. Managed by `python/helpers/auth_db.py` and `python/helpers/user_store.py`.

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `AUTH_DATABASE_URL` | SQLAlchemy connection string for the auth database | SQLAlchemy URL | `sqlite:///usr/auth.db` | No |
| `VAULT_MASTER_KEY` | Master encryption key for the API key vault (AES-256-GCM via `python/helpers/vault_crypto.py`). Required for OIDC token cache encryption. | 64-char hex string (256 bits) | *(none)* | For OIDC + vault |
| `ADMIN_EMAIL` | Bootstrap admin email; creates an admin account on first launch if set | Email address | *(none)* | No |
| `ADMIN_PASSWORD` | Bootstrap admin password; used with `ADMIN_EMAIL` on first launch | Any string | *(none)* | With `ADMIN_EMAIL` |

**Generating secure values:**

```bash
# VAULT_MASTER_KEY — 256-bit AES key (64-char hex)
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## EntraID OIDC SSO

Microsoft Entra ID (Azure AD) app registration for single sign-on via OIDC authorization-code flow. Managed by `python/helpers/auth.py` (AuthManager). When all four OIDC variables are set, the login page shows a "Sign in with Microsoft" SSO button alongside the local login form.

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `OIDC_TENANT_ID` | Microsoft Entra tenant ID | UUID | *(none)* | For OIDC |
| `OIDC_CLIENT_ID` | Entra app registration client ID | UUID | *(none)* | For OIDC |
| `OIDC_CLIENT_SECRET` | Entra app registration client secret | String | *(none)* | For OIDC |
| `OIDC_REDIRECT_URI` | Explicit OIDC callback URL; auto-generated from Flask `url_for` if unset. Set explicitly in production behind a reverse proxy. | URL | *(auto: `/auth/callback`)* | No |

**Setup steps:**

1. Register an app in Microsoft Entra ID (Azure Portal > App registrations)
2. Set redirect URI to `https://your-domain/auth/callback`
3. Create a client secret
4. Set `OIDC_TENANT_ID`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` in `usr/.env`
5. Set `VAULT_MASTER_KEY` for encrypted MSAL token cache persistence

### SSO Auto-Assignment

Controls automatic membership provisioning for JIT-provisioned SSO users who don't have EntraID group mappings configured.

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `A0_SET_SSO_AUTO_ASSIGN` | Auto-assign SSO users to the default org/team on first login | `true`, `false` | `true` | No |
| `A0_SET_SSO_DEFAULT_ROLE` | Role assigned to auto-provisioned SSO users | `member`, `viewer` | `member` | No |

When enabled (default), SSO users immediately have access after authenticating. When disabled, SSO users receive 403 until an admin assigns them via the admin API or EntraID group mappings are configured.

### SSO Group Mapping Bootstrap

Seed EntraID group-to-org/team mappings at startup via environment variable, eliminating the need for manual admin API calls. Mappings are upserted (created or updated) on every startup, making this safe for repeated runs.

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `A0_SET_SSO_GROUP_MAPPINGS` | Semicolon-delimited EntraID group mapping definitions | See format below | _(empty)_ | No |

**Format:** `entra_group_id:org_slug:team_slug:role` entries separated by semicolons.

| Field | Required | Description |
|-------|----------|-------------|
| `entra_group_id` | Yes | Azure AD security group Object ID (GUID from Azure Portal) |
| `org_slug` | Yes | Organization slug to map to (e.g., `default`) |
| `team_slug` | No | Team slug within the org (empty = org-level mapping only) |
| `role` | No | Role to assign: `owner`, `admin`, `lead`, `member` (default), `viewer` |

**Example:**

```bash
# Map two Azure AD groups to the default org/team with different roles
A0_SET_SSO_GROUP_MAPPINGS="e1a2b3c4-...:default:default:member;f5d6e7a8-...:default:default:team_lead"

# Org-level mapping only (no team assignment)
A0_SET_SSO_GROUP_MAPPINGS="a9b0c1d2-...:default::org_admin"
```

> **Note:** Orgs and teams referenced by slug must already exist (created via admin API or the default bootstrap). Invalid entries (unknown slugs, malformed format) are logged as warnings and skipped without blocking startup. Mappings defined here are additive — they do not remove mappings configured via the admin API.

### EntraID Group-Based Role Assignment

For production deployments, you can map EntraID security groups to local org/team memberships with specific roles. This gives fine-grained control over who gets what access level — different Azure groups can map to different roles (owner, admin, member, viewer).

**Step 1: Configure group claims in Azure Portal**

1. Go to **Azure Portal** > **App registrations** > your OIDC SSO app
2. Select **Token configuration** > **Add groups claim**
3. Select **Security groups** (or **All groups** if using Microsoft 365 groups)
4. Under **ID token**, check **Group ID**
5. Click **Add**

If your tenant has users in more than 200 groups, Entra ID uses a "group overage" claim instead of embedding all group IDs. The app automatically handles this by fetching groups from the Microsoft Graph API using the access token.

> **Graph API permissions (optional, for group overage):** If your users belong to >200 groups, add the `GroupMember.Read.All` delegated permission to your app registration and grant admin consent. This allows the app to fetch the full group list when the ID token uses overage.

**Step 2: Create group mappings via the admin API**

Map each EntraID security group to a local organization and (optionally) team with a role:

```bash
# List organizations to find the default org ID
curl -X POST http://localhost:5000/admin_orgs \
  -H "Content-Type: application/json" \
  -b <admin-session-cookie> \
  -d '{"action": "list"}'

# List teams within that org
curl -X POST http://localhost:5000/admin_teams \
  -H "Content-Type: application/json" \
  -b <admin-session-cookie> \
  -d '{"action": "list", "org_id": "<ORG_ID>"}'

# Map an EntraID group → org/team with role
curl -X POST http://localhost:5000/admin_group_mappings \
  -H "Content-Type: application/json" \
  -b <admin-session-cookie> \
  -d '{
    "action": "upsert",
    "entra_group_id": "<AZURE-SECURITY-GROUP-OBJECT-ID>",
    "org_id": "<ORG_ID>",
    "team_id": "<TEAM_ID>",
    "role": "member"
  }'
```

Find the Azure security group's Object ID in **Azure Portal** > **Groups** > select the group > **Overview** > **Object Id**.

**Step 3: Disable auto-assignment (optional)**

Once group mappings are configured, disable auto-assignment so that only users in mapped groups get access:

```bash
# usr/.env
A0_SET_SSO_AUTO_ASSIGN=false
```

**Available roles:**

| Role | Org-level | Team-level | Description |
|------|-----------|------------|-------------|
| `owner` | `org_owner` | — | Full access to all org resources |
| `admin` | `org_admin` | — | Manage org settings, admin panel, MCP, knowledge |
| `lead` | — | `team_lead` | Full access within team scope |
| `member` | `member` | `member` | Standard access: create chats, read settings, upload knowledge |
| `viewer` | `viewer` | `viewer` | Read-only access |

Roles cascade: when a group mapping specifies `role: "admin"` at the org level, the user gets `org_admin` Casbin policies. At the team level, the same user needs a separate team mapping (or auto-assignment) for team-scoped resources.

**How it works at login:**

1. User authenticates via Entra ID SSO
2. `process_callback()` extracts group IDs from the ID token claims (or fetches via Graph API)
3. `sync_group_memberships()` looks up each group ID in the `entra_group_mappings` table
4. For each match, creates/updates `OrgMembership` and `TeamMembership` records with the mapped role
5. Removes team memberships for groups the user is no longer in (group sync is idempotent)
6. `sync_user_roles()` reads the memberships and creates Casbin grouping policies
7. RBAC enforcement uses those policies for every API request

## MCP Server OAuth (Inbound Auth)

Optional Entra ID OAuth for inbound MCP connections (IDE clients like VS Code, Cursor, Claude Code). Managed by `python/helpers/mcp_server.py` via FastMCP's `AzureProvider`. When all three required variables are set, the MCP server accepts OAuth Bearer tokens alongside the existing token-in-path authentication.

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `MCP_AZURE_CLIENT_ID` | Azure App Registration client ID for the MCP API (separate from OIDC app registration) | UUID | *(none)* | For MCP OAuth |
| `MCP_AZURE_CLIENT_SECRET` | Client secret for the MCP Azure app | String | *(none)* | For MCP OAuth |
| `MCP_AZURE_TENANT_ID` | Entra ID tenant (GUID, "organizations", or "consumers"; NOT "common") | UUID or keyword | *(none)* | For MCP OAuth |
| `MCP_SERVER_BASE_URL` | Public URL of the server (including protocol). Used for OAuth callbacks. | URL | `http://localhost:50080` | Production |
| `MCP_AZURE_IDENTIFIER_URI` | Application ID URI for scope prefixing | URI | `api://{MCP_AZURE_CLIENT_ID}` | No |
| `MCP_AZURE_REDIRECT_URIS` | Comma-separated allowed client redirect URIs | URL list | *(none — all allowed)* | No |
| `MCP_AZURE_JWT_SIGNING_KEY` | Persistent key for signing OAuth proxy tokens (survives server restarts) | String | *(none — random per restart)* | Production |

**Setup steps:**

1. Register a **separate** app in Microsoft Entra ID (Azure Portal > App registrations)
2. Add redirect URIs for your IDE clients
3. Under "Expose an API", set the Application ID URI (`api://{client-id}`) and add scopes: `discover`, `tools.read`, `tools.execute`, `chat`
4. Create a client secret
5. Set `MCP_AZURE_CLIENT_ID`, `MCP_AZURE_CLIENT_SECRET`, `MCP_AZURE_TENANT_ID` in `usr/.env`
6. Set `MCP_SERVER_BASE_URL` and `MCP_AZURE_JWT_SIGNING_KEY` for production

**Generating secure values:**

```bash
# MCP_AZURE_JWT_SIGNING_KEY — persistent signing key
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Server & Networking

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `WEB_UI_HOST` | Host/IP address for the web UI server | IP or hostname | `localhost` | No |
| `WEB_UI_PORT` | Port for the web UI server | Integer | `5000` | No |
| `TUNNEL_API_PORT` | Port for the tunnel proxy API | Integer | `0` (disabled) | No |
| `FLASK_MAX_CONTENT_LENGTH` | Max upload size in bytes | Integer | `157286400` (150 MB) | No |
| `FLASK_MAX_FORM_MEMORY_SIZE` | Max form field size in bytes | Integer | `157286400` (150 MB) | No |

## API Keys (Provider Authentication)

API keys follow the primary pattern `API_KEY_{PROVIDER}` where `{PROVIDER}` matches the provider ID in `conf/model_providers.yaml` (uppercased). This is the format the app writes when saving via the web UI. Apollos AI also accepts the alternative patterns `{PROVIDER}_API_KEY` and `{PROVIDER}_API_TOKEN`.

| Variable (primary format) | Description | Required |
|---------------------------|-------------|----------|
| `API_KEY_A0_VENICE` | Apollos AI API (Venice-backed) key | When using Apollos AI API provider |
| `API_KEY_ANTHROPIC` | Anthropic API key | When using Anthropic provider |
| `API_KEY_AZURE` | Azure OpenAI API key | When using Azure provider |
| `API_KEY_BEDROCK` | AWS Bedrock API key | When using AWS Bedrock provider |
| `API_KEY_COMETAPI` | CometAPI API key | When using CometAPI provider |
| `API_KEY_DEEPSEEK` | DeepSeek API key | When using DeepSeek provider |
| `API_KEY_GITHUB_COPILOT` | GitHub Copilot API key | When using GitHub Copilot provider |
| `API_KEY_GOOGLE` | Google/Gemini API key | When using Google provider |
| `API_KEY_GROQ` | Groq API key | When using Groq provider |
| `API_KEY_HUGGINGFACE` | HuggingFace API key | When using HuggingFace provider |
| `API_KEY_LITELLM_PROXY` | LiteLLM Proxy API key | When using LiteLLM Proxy provider |
| `API_KEY_LM_STUDIO` | LM Studio API key | When using LM Studio provider |
| `API_KEY_MISTRAL` | Mistral AI API key | When using Mistral provider |
| `API_KEY_MOONSHOT` | Moonshot AI API key | When using Moonshot provider |
| `API_KEY_OLLAMA` | Ollama API key | When using Ollama provider |
| `API_KEY_OPENAI` | OpenAI API key | When using OpenAI provider |
| `API_KEY_OPENROUTER` | OpenRouter API key | When using OpenRouter provider |
| `API_KEY_OTHER` | API key for "Other OpenAI compatible" provider | When using Other provider |
| `API_KEY_SAMBANOVA` | Sambanova API key | When using Sambanova provider |
| `API_KEY_VENICE` | Venice.ai API key | When using Venice provider |
| `API_KEY_XAI` | xAI API key | When using xAI provider |
| `API_KEY_ZAI` | Z.AI API key | When using Z.AI provider |
| `API_KEY_ZAI_CODING` | Z.AI Coding API key | When using Z.AI Coding provider |

## API Base URLs (Provider Endpoints)

Custom base URLs follow the pattern `{PROVIDER}_API_BASE` (uppercased). These override the YAML defaults but are overridden by the UI settings API Base field.

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_VENICE_API_BASE` | Base URL for Apollos AI API | `https://llm.apollos-ai.ai/v1` (from YAML) |
| `LITELLM_PROXY_API_BASE` | Base URL for LiteLLM Proxy | `http://localhost:4000/v1` (from YAML) |
| `VENICE_API_BASE` | Base URL for Venice.ai | `https://api.venice.ai/api/v1` (from YAML) |
| `ZAI_API_BASE` | Base URL for Z.AI | `https://api.z.ai/api/paas/v4` (from YAML) |
| `ZAI_CODING_API_BASE` | Base URL for Z.AI Coding | `https://api.z.ai/api/coding/paas/v4` (from YAML) |
| `{PROVIDER}_API_BASE` | Base URL for any provider (generic pattern) | Provider-specific or empty |

## Apollos AI Internal

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `A0_PERSISTENT_RUNTIME_ID` | Persistent runtime identifier; auto-generated on first run and saved to `usr/.env` for reuse across restarts | Hex string (32 chars) | Auto-generated via `secrets.token_hex(16)` | No |
| `A0_WS_DEBUG` | Enable verbose WebSocket debug logging | `1`, `true`, `yes`, `on` | *(disabled)* | No |
| `A2A_TOKEN` | Bearer token for Agent-to-Agent (A2A) protocol authentication; sent as `Authorization: Bearer <token>` and `X-API-KEY` header. Read via `os.getenv()`, not dotenv | Any string | *(empty)* | When using A2A |
| `DEFAULT_USER_TIMEZONE` | Default timezone; auto-written from browser on first visit | IANA tz name | `UTC` | No |
| `DEFAULT_USER_UTC_OFFSET_MINUTES` | UTC offset in minutes; auto-written from browser on first visit | Integer | `0` | No |

**Generating secure values:**

```bash
# A2A_TOKEN — URL-safe bearer token for A2A protocol authentication
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## LiteLLM & Model Runtime

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `ANONYMIZED_TELEMETRY` | Disable browser-use library telemetry; auto-written to `usr/.env` at startup | `true`, `false` | `false` (auto-set) | No |
| `LITELLM_LOG` | LiteLLM logging verbosity (set by Apollos AI at startup) | `DEBUG`, `INFO`, `ERROR` | `ERROR` | No |
| `KMP_DUPLICATE_LIB_OK` | Set to `TRUE` to prevent OMP Error #15 crash caused by duplicate `libomp.dylib` libraries bundled in faiss, torch, and sklearn on macOS; automatically set at startup | `TRUE`, `FALSE` | `TRUE` (set at startup) | No |
| `TOKENIZERS_PARALLELISM` | HuggingFace tokenizers parallelism (set at startup to avoid fork warnings) | `true`, `false` | `false` | No |
| `TZ` | System timezone (set at startup) | IANA tz name | `UTC` | No |
| `USER_AGENT` | HTTP User-Agent for unstructured document processing | Any string | `@mixedbread-ai/unstructured` | No |

## Settings Overrides (`A0_SET_*`)

Any UI setting can be overridden via environment variable using the prefix `A0_SET_`. The value is type-coerced to match the setting's default type (bool, int, float, string, JSON dict). Case-insensitive lookup: both `A0_SET_chat_model_provider` and `A0_SET_CHAT_MODEL_PROVIDER` work.

### Chat Model

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_CHAT_MODEL_PROVIDER` | Chat model provider ID | `openrouter` |
| `A0_SET_CHAT_MODEL_NAME` | Chat model name | `google/gemini-3-pro-preview` |
| `A0_SET_CHAT_MODEL_API_BASE` | Chat model API base URL | *(empty)* |
| `A0_SET_CHAT_MODEL_KWARGS` | Chat model extra params (JSON) | `{"temperature": "0"}` |
| `A0_SET_CHAT_MODEL_CTX_LENGTH` | Chat model context window size | `100000` |
| `A0_SET_CHAT_MODEL_CTX_HISTORY` | Fraction of context used for history | `0.7` |
| `A0_SET_CHAT_MODEL_VISION` | Enable vision/image support | `true` |
| `A0_SET_CHAT_MODEL_RL_REQUESTS` | Rate limit: max requests (0 = unlimited) | `0` |
| `A0_SET_CHAT_MODEL_RL_INPUT` | Rate limit: max input tokens (0 = unlimited) | `0` |
| `A0_SET_CHAT_MODEL_RL_OUTPUT` | Rate limit: max output tokens (0 = unlimited) | `0` |

### Utility Model

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_UTIL_MODEL_PROVIDER` | Utility model provider ID | `openrouter` |
| `A0_SET_UTIL_MODEL_NAME` | Utility model name | `google/gemini-3-flash-preview` |
| `A0_SET_UTIL_MODEL_API_BASE` | Utility model API base URL | *(empty)* |
| `A0_SET_UTIL_MODEL_KWARGS` | Utility model extra params (JSON) | `{"temperature": "0"}` |
| `A0_SET_UTIL_MODEL_CTX_LENGTH` | Utility model context window size | `100000` |
| `A0_SET_UTIL_MODEL_CTX_INPUT` | Fraction of context used for input | `0.7` |
| `A0_SET_UTIL_MODEL_RL_REQUESTS` | Rate limit: max requests | `0` |
| `A0_SET_UTIL_MODEL_RL_INPUT` | Rate limit: max input tokens | `0` |
| `A0_SET_UTIL_MODEL_RL_OUTPUT` | Rate limit: max output tokens | `0` |

### Embedding Model

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_EMBED_MODEL_PROVIDER` | Embedding model provider ID | `huggingface` |
| `A0_SET_EMBED_MODEL_NAME` | Embedding model name | `sentence-transformers/all-MiniLM-L6-v2` |
| `A0_SET_EMBED_MODEL_API_BASE` | Embedding model API base URL | *(empty)* |
| `A0_SET_EMBED_MODEL_KWARGS` | Embedding model extra params (JSON) | `{}` |
| `A0_SET_EMBED_MODEL_RL_REQUESTS` | Rate limit: max requests | `0` |
| `A0_SET_EMBED_MODEL_RL_INPUT` | Rate limit: max input tokens | `0` |

### Browser Model

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_BROWSER_MODEL_PROVIDER` | Browser model provider ID | `openrouter` |
| `A0_SET_BROWSER_MODEL_NAME` | Browser model name | `google/gemini-3-pro-preview` |
| `A0_SET_BROWSER_MODEL_API_BASE` | Browser model API base URL | *(empty)* |
| `A0_SET_BROWSER_MODEL_KWARGS` | Browser model extra params (JSON) | `{"temperature": "0"}` |
| `A0_SET_BROWSER_MODEL_VISION` | Enable vision for browser model | `true` |
| `A0_SET_BROWSER_HTTP_HEADERS` | Extra HTTP headers for browser (JSON) | `{}` |
| `A0_SET_BROWSER_MODEL_RL_REQUESTS` | Rate limit: max requests | `0` |
| `A0_SET_BROWSER_MODEL_RL_INPUT` | Rate limit: max input tokens | `0` |
| `A0_SET_BROWSER_MODEL_RL_OUTPUT` | Rate limit: max output tokens | `0` |

### Memory & Recall

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_MEMORY_RECALL_ENABLED` | Enable automatic memory recall | `true` |
| `A0_SET_MEMORY_RECALL_DELAYED` | Delay recall until after first response | `false` |
| `A0_SET_MEMORY_RECALL_INTERVAL` | Recall every N messages | `3` |
| `A0_SET_MEMORY_RECALL_HISTORY_LEN` | Max history tokens used for recall queries | `10000` |
| `A0_SET_MEMORY_RECALL_MEMORIES_MAX_SEARCH` | Max memory entries to search | `12` |
| `A0_SET_MEMORY_RECALL_SOLUTIONS_MAX_SEARCH` | Max solution entries to search | `8` |
| `A0_SET_MEMORY_RECALL_MEMORIES_MAX_RESULT` | Max memory entries returned | `5` |
| `A0_SET_MEMORY_RECALL_SOLUTIONS_MAX_RESULT` | Max solution entries returned | `3` |
| `A0_SET_MEMORY_RECALL_SIMILARITY_THRESHOLD` | Minimum cosine similarity for recall | `0.7` |
| `A0_SET_MEMORY_RECALL_QUERY_PREP` | Use LLM to prepare recall queries | `false` |
| `A0_SET_MEMORY_RECALL_POST_FILTER` | Use LLM to post-filter recalled memories | `false` |
| `A0_SET_MEMORY_MEMORIZE_ENABLED` | Enable automatic memorization | `true` |
| `A0_SET_MEMORY_MEMORIZE_CONSOLIDATION` | Enable memory consolidation/dedup | `true` |
| `A0_SET_MEMORY_MEMORIZE_REPLACE_THRESHOLD` | Cosine similarity threshold for replacing similar memories | `0.9` |

### Agent & Workspace

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_AGENT_PROFILE` | Default agent profile subdirectory | `apollos` |
| `A0_SET_AGENT_MEMORY_SUBDIR` | Memory storage subdirectory | `default` |
| `A0_SET_AGENT_KNOWLEDGE_SUBDIR` | Knowledge base subdirectory | `custom` |
| `A0_SET_WORKDIR_PATH` | Working directory path | `usr/workdir` |
| `A0_SET_WORKDIR_GITIGNORE` | Gitignore patterns for working directory listing | *(auto-generated)* |
| `A0_SET_WORKDIR_SHOW` | Show working directory contents in prompt | `true` |
| `A0_SET_WORKDIR_MAX_DEPTH` | Max directory tree depth | `5` |
| `A0_SET_WORKDIR_MAX_FILES` | Max files shown per directory | `20` |
| `A0_SET_WORKDIR_MAX_FOLDERS` | Max folders shown per directory | `20` |
| `A0_SET_WORKDIR_MAX_LINES` | Max lines shown per file | `250` |

### Code Execution (RFC)

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_RFC_AUTO_DOCKER` | Auto-start Docker execution container | `true` |
| `A0_SET_RFC_URL` | RFC server hostname | `localhost` |
| `A0_SET_RFC_PORT_HTTP` | RFC HTTP port | `55080` |
| `A0_SET_RFC_PORT_SSH` | RFC SSH port | `55022` |
| `A0_SET_SHELL_INTERFACE` | Shell interface type | `local` (Docker) / `ssh` (dev) |

### Speech & TTS

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_STT_MODEL_SIZE` | Whisper model size | `base` |
| `A0_SET_STT_LANGUAGE` | Speech-to-text language | `en` |
| `A0_SET_STT_SILENCE_THRESHOLD` | Silence detection threshold | `0.3` |
| `A0_SET_STT_SILENCE_DURATION` | Silence duration before stop (ms) | `1000` |
| `A0_SET_STT_WAITING_TIMEOUT` | Waiting timeout before stop (ms) | `2000` |
| `A0_SET_TTS_KOKORO` | Use Kokoro TTS engine | `true` |

### MCP & A2A Servers

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_MCP_SERVERS` | MCP server configurations (JSON) | `{"mcpServers": {}}` |
| `A0_SET_MCP_CLIENT_INIT_TIMEOUT` | MCP client initialization timeout (seconds) | `10` |
| `A0_SET_MCP_CLIENT_TOOL_TIMEOUT` | MCP tool execution timeout (seconds) | `120` |
| `A0_SET_MCP_SERVER_ENABLED` | Enable built-in MCP server | `false` |
| `A0_SET_A2A_SERVER_ENABLED` | Enable Agent-to-Agent server | `false` |

### Miscellaneous

| Variable | Description | Default |
|----------|-------------|---------|
| `A0_SET_WEBSOCKET_SERVER_RESTART_ENABLED` | Broadcast server restart events to clients | `true` |
| `A0_SET_UVICORN_ACCESS_LOGS_ENABLED` | Enable uvicorn HTTP access logs | `false` |
| `A0_SET_LITELLM_GLOBAL_KWARGS` | Global LiteLLM kwargs applied to all models (JSON) | `{}` |
| `A0_SET_UPDATE_CHECK_ENABLED` | Check for updates on startup | `true` |

### Internal (Auto-Managed)

These settings exist in the `Settings` TypedDict but are auto-managed by the application. They should not be overridden via `A0_SET_*` environment variables.

| Variable | Description | Managed By |
|----------|-------------|------------|
| `A0_SET_MCP_SERVER_TOKEN` | MCP/A2A server authentication token | Auto-generated (`create_auth_token()`) on first run |
| `A0_SET_VARIABLES` | User-defined template variables | Settings > Variables UI tab |
| `A0_SET_SECRETS` | User-defined secrets content | Settings > Secrets UI tab (stored in `usr/secrets.env`) |

## Secrets Store (`usr/secrets.env`)

Apollos AI has a dedicated secrets file at `usr/secrets.env`, separate from `usr/.env`. This file is managed through the web UI (Settings > Secrets) and supports:

- Standard `.env` key-value format
- `§§secret(KEY)` placeholder syntax for agents to reference secrets without exposing raw values
- Streaming output masking to prevent secret leakage in LLM responses
- Per-project secrets in `.a0proj/secrets.env` (when using Projects)

> **Do not edit `usr/secrets.env` manually** — use the Settings UI instead. The merge logic preserves comments and key ordering.

## Branding Configuration

Customize the project identity displayed in the UI, notifications, HTTP headers, and LLM prompts. All values are optional. Default values create an "Apollos AI" branded experience.

These variables are read by `python/helpers/branding.py` at import time and used across the application wherever the project name, URL, or GitHub link appears.

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BRAND_NAME` | Display name shown in the UI, browser title, HTTP headers, and system prompts | `Apollos AI` | No |
| `BRAND_SLUG` | URL-safe and filename-safe identifier used in paths and generated assets | `apollos-ai` | No |
| `BRAND_URL` | Project website URL displayed in the UI footer and about pages | `https://apollos.ai` | No |
| `BRAND_GITHUB_URL` | GitHub repository URL used for source links and update checks | `https://github.com/jrmatherly/apollos-ai` | No |
| `BRAND_UPDATE_CHECK_URL` | URL for update version checks; set to empty string to disable | `https://api.github.com/repos/jrmatherly/apollos-ai/releases/latest` | No |

**Example — custom branding for a white-label deployment:**

```bash
# In usr/.env
BRAND_NAME=My Custom AI
BRAND_SLUG=my-custom-ai
BRAND_URL=https://mycustomai.example.com
BRAND_GITHUB_URL=https://github.com/myorg/my-custom-ai
```

## Docker & Container

Used when running Apollos AI in Docker. See `Dockerfile`, `DockerfileLocal`, and `docker/run/`.

| Variable | Description | Values | Default | Required |
|----------|-------------|--------|---------|----------|
| `BRANCH` | Git branch to build from; `local` uses local files instead of cloning | Branch name or `local` | `local` (DockerfileLocal) / *(none)* (production) | Build-time |
| `DEBUG` | Enable verbose logging in supervisord event listener | Any value | *(disabled)* | No |
| `SEARXNG_SETTINGS_PATH` | Path to SearXNG configuration file | File path | `/etc/searxng/settings.yml` | No |
| `SEARXNG_SECRET` | Secret key for SearXNG instance security. Overrides the `secret_key` in SearXNG's `settings.yml`. | Any string | *(none)* | When using SearXNG |

**Generating secure values:**

```bash
# SEARXNG_SECRET — random secret for SearXNG Flask app
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Email Test Variables

Used only by `tests/email_parser_test.py`:

| Variable | Description | Default |
|----------|-------------|---------|
| `TEST_SERVER_TYPE` | Email server type | `imap` |
| `TEST_EMAIL_SERVER` | Email server hostname | *(none)* |
| `TEST_EMAIL_PORT` | Email server port | `993` |
| `TEST_EMAIL_USERNAME` | Email account username | *(none)* |
| `TEST_EMAIL_PASSWORD` | Email account password | *(none)* |
