# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Apollos AI (branded as configurable via `BRAND_NAME` env var, default "Apollos AI") is a personal organic agentic AI framework (Python backend, Alpine.js frontend). Fork of `agent0ai/agent-zero`, remote at `jrmatherly/apollos-ai`.

## Commands

All tooling is managed by **mise** (`mise.toml`). Use `mise run <task>` for everything.

```bash
mise run r                 # Start UI server (alias for run)
mise run t                 # Run tests (alias for test)
mise run lint              # Lint all (Ruff + Biome)
mise run lint:python       # Lint Python only
mise run lint:css          # Lint CSS only
mise run format:check      # Check formatting (CI mode)
mise run format            # Auto-format all
mise run ci                # Full CI: lint + format check + test
mise run setup             # First-time: deps + playwright + hooks
mise run install           # Install Python deps (uv sync)
mise run hooks:check       # Run hk pre-commit checks manually
mise run deps:add <pkg>    # Add dependency + regenerate requirements.txt
```

Docker builds (3 images: base, app, local):

```bash
mise run docker:build:base          # Build base image (Kali + system packages)
mise run docker:build:app           # Build app image from main branch
mise run docker:build:app testing   # Build app image from a specific branch
mise run docker:build:local         # Build local dev image from working tree
mise run docker:build               # Build base + local in order
mise run docker:push:base           # Build + push base image to GHCR
mise run docker:push:app            # Build + push app image to GHCR
mise run docker:run                 # Run local container (port 50080→80)
```

Single test: `mise run t -- tests/test_websocket_manager.py -v`

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions are auto-detected.

## Architecture

**Entry point**: `run_ui.py` → Flask + uvicorn (ASGI) + python-socketio

**Core loop** (`agent.py`): The Agent operates in a monologue loop — build prompt → call LLM → parse JSON → execute tool → repeat. Loop ends when the `response` tool is called.

**Auto-discovery pattern**: Tools (`python/tools/`), API handlers (`python/api/`), and WebSocket handlers (`python/websocket_handlers/`) are auto-loaded by scanning their directories. Drop a file in, it's active.

**Extension system** (`python/extensions/`): 24 lifecycle hook directories (e.g., `message_loop_start/`, `tool_execute_before/`). Extensions are sorted by filename prefix (`_10_`, `_20_`). User overrides go in `usr/extensions/` with the same filename.

**Models** (`models.py`): LiteLLM multi-provider config. Four model types: chat, utility, embedding, browser. Configured via UI settings → `initialize.py` → `AgentConfig`.

**Prompts** (`prompts/`): Markdown templates with `{{ include }}` for composition and `{{variable}}` for substitution.

**Memory**: FAISS vector DB with configurable embeddings (default: sentence-transformers local; supports remote providers via LiteLLM). Used by `memory_save`/`memory_load` tools and recall extensions.

**Branding**: Centralized in `python/helpers/branding.py` with 5 env vars (`BRAND_NAME`, `BRAND_SLUG`, `BRAND_URL`, `BRAND_GITHUB_URL`, `BRAND_UPDATE_CHECK_URL`). Frontend gets values via `/branding_get` API → Alpine.js store (`webui/js/branding-store.js`). Prompt templates use `{{brand_name}}` variable injection.

## Conventions

- **Python**: `snake_case` functions, `PascalCase` classes, `str | None` unions (not `Optional`)
- **New tool**: Extend `Tool` in `python/tools/`, implement `async execute(**kwargs) -> Response`
- **New API endpoint**: Extend `ApiHandler` in `python/api/`, implement `async process(input, request) -> dict`
- **New extension**: Extend `Extension` in the appropriate `python/extensions/<hook>/` dir, prefix-sorted filename
- **New WebSocket handler**: Extend handler class in `python/websocket_handlers/`, auto-discovered by namespace
- **Disabled files**: `._py` suffix = archived/disabled
- **Commits**: Conventional Commits enforced by hk hook (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`, `ci:`, `style:`, `perf:`, `security:`)

## Dependencies

- **Source of truth**: `pyproject.toml` (managed by uv)
- **Lockfile**: `uv.lock` (committed)
- **Docker compat**: `requirements.txt` — auto-generated, never edit manually
- **Add a dep**: `mise run deps:add <pkg>` (adds to pyproject.toml + regenerates requirements.txt)
- **Version override**: `[tool.uv] override-dependencies` in pyproject.toml for conflict resolution

## CI/CD

Nine GitHub Actions workflows in `.github/workflows/`:
- **ci.yml**: Lint + format check + test (parallel jobs) on push/PR to main; paths-ignore skips docs-only changes; concurrency groups cancel stale runs; uv cache on test job
- **claude.yml**: Claude Code agent for issue/PR comment responses and assigned issues
- **claude-code-review.yml**: Claude Code automated PR review on open/sync/ready
- **drift.yml**: DriftDetect codebase analysis (disabled — manual dispatch only)
- **release.yml**: git-cliff changelog + GitHub release on `v*` tag push; builds & pushes Docker app image (amd64) to GHCR
- **docker-base.yml**: Builds & pushes Docker base image to GHCR on `docker/base/**` changes or manual dispatch
- **hooks-check.yml**: hk validation on PRs to main
- **codeql.yml**: CodeQL security analysis (Python) on push/PR to main + weekly schedule
- **dependency-review.yml**: Dependency vulnerability review + requirements.txt sync check on PRs

Additional GitHub configuration:
- **dependabot.yml**: Weekly automated dependency updates for uv (Python), GitHub Actions, and Docker base images
- **ISSUE_TEMPLATE/**: Structured bug report and feature request forms (YAML)
- **pull_request_template.md**: PR checklist template

All CI workflows use `jdx/mise-action@v3` for tool installation; security workflows use dedicated actions.

## Environment Variables

- **Reference**: `docs/reference/environment-variables.md` — complete catalog of all env vars
- **Example file**: `usr/.env.example` — annotated template (copy to `usr/.env`)
- **API keys**: `{PROVIDER}_API_KEY` pattern, matching provider IDs in `conf/model_providers.yaml`
- **Settings overrides**: `A0_SET_{setting_name}` prefix overrides any UI setting
- **Base URLs**: `{PROVIDER}_API_BASE` overrides YAML defaults

## DriftDetect

`.drift/` contains codebase pattern analysis artifacts. The `patterns/approved/` directory and config are committed; `memory/`, `cache/`, `lake/`, `history/` are gitignored. Run `mise run drift:scan` to analyze, `mise run drift:gate` for quality gates.

## Authentication

Four-phase auth system:

- **Auth DB**: `auth_db.py` (SQLAlchemy), `user_store.py` (ORM + CRUD), `alembic/` (migrations)
- **OIDC**: `auth.py` (MSAL/Entra ID), env: `OIDC_TENANT_ID`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`
- **Local login**: Argon2id hashing, fallback from OIDC
- **Tenant isolation**: `tenant.py` (TenantContext), multi-user data scoping
- **RBAC**: `rbac.py` + `conf/rbac_model.conf` (Casbin)
- **Vault**: `vault_crypto.py` (AES-256-GCM, HKDF), env: `VAULT_MASTER_KEY`
- **Bootstrap**: `auth_bootstrap.py` creates admin from `ADMIN_EMAIL`/`ADMIN_PASSWORD`
- **Session**: `session["user"] = {id, email, name, auth_method}`
- **Routes**: `/login`, `/login/entra`, `/auth/callback`, `/logout`
- **Legacy compat**: `AUTH_LOGIN`/`AUTH_PASSWORD` still works as single-user fallback
- **Migrations**: `uv run alembic upgrade head` (run automatically by bootstrap)

## Platform Integrations

Inbound webhook receivers for Slack, GitHub, and Jira. Events are processed by the agent and responses are delivered back to the originating platform. See `docs/integrations/` for per-platform setup guides.

**Webhook Handlers** (auto-discovered in `python/api/`):
- `webhook_slack.py` — Slack Events API (app_mention, DM); signing secret + timestamp replay protection
- `webhook_slack_oauth.py` — Slack OAuth identity linking
- `webhook_github.py` — GitHub App webhooks (issues, PRs, comments); HMAC-SHA256 verification
- `webhook_jira.py` — Jira Cloud webhooks (issue created/updated, comments); shared secret via query param

**Core Infrastructure** (`python/helpers/`):
- `integration_models.py` — Pydantic models: `SourceType`, `IntegrationMessage`, `WebhookContext`, `CallbackRegistration`, `CallbackStatus`
- `webhook_verify.py` — Platform-specific signature verification
- `callback_registry.py` — Thread-safe singleton callback store
- `callback_retry.py` — Exponential backoff retry for failed deliveries
- `webhook_event_log.py` — Bounded in-memory audit log
- `jira_markup.py` — Markdown-to-Jira wiki markup converter

**Extension**: `python/extensions/monologue_end/_80_integration_callback.py` — routes agent responses to Slack/GitHub/Jira

**API Endpoints**: `callback_admin.py` (list/retry failed callbacks), `webhook_events_get.py` (event log query), `integration_settings_get.py` (masked settings read)

**Settings UI**: `webui/components/settings/integrations/integrations-settings.html` — Integrations tab in Settings

**Settings** (via `A0_SET_*` env vars or UI): `integrations_enabled`, `slack_signing_secret`, `slack_bot_token`, `github_webhook_secret`, `github_app_id`, `jira_webhook_secret`, `jira_site_url`

## MCP Gateway

Built-in MCP gateway with multi-server composition, discovery, lifecycle management, and access control:

**Infrastructure (Phase 1):**
- **Connection Pool**: `python/helpers/mcp_connection_pool.py` — persistent MCP sessions with health checking
- **Resource Store**: `python/helpers/mcp_resource_store.py` — pluggable backend (InMemory dev, extensible to Redis/Postgres)
- **Identity Headers**: `python/helpers/mcp_identity.py` — X-Mcp-UserId/UserName/Roles injection, auth header stripping
- **Container Manager**: `python/helpers/mcp_container_manager.py` — Docker lifecycle for MCP server containers
- **Permission Model**: Resource-level RBAC (creator + admin + required_roles) per MCP server
- **Proxy**: `DynamicMcpProxy` in `mcp_server.py` — ASGI reverse proxy at `/mcp`, routes SSE/HTTP/OAuth

**Composition & Runtime (Phase 2):**
- **Compositor**: `python/helpers/mcp_gateway_compositor.py` — FastMCP 3.0 multi-server mounting with `create_proxy()`, wired into DynamicMcpProxy
- **Health Checker**: `python/helpers/mcp_gateway_health.py` — pool health checks + Docker container status monitoring
- **Lifecycle Hooks**: `python/helpers/mcp_gateway_lifecycle.py` — server create/delete side effects (mount/unmount, Docker start/stop, pool eviction)
- **Registry Client**: `python/helpers/mcp_registry_client.py` — async httpx client for MCP Registry API (`registry.modelcontextprotocol.io`)
- **Docker Catalog**: `python/helpers/docker_mcp_catalog.py` — YAML parser for `docker mcp catalog show` output
- **Tool Index**: `python/helpers/mcp_tool_index.py` — keyword-searchable index of tools across all mounted MCP servers

**API Endpoints:**
- `python/api/mcp_gateway_servers.py` — CRUD for gateway servers (list/create/update/delete/status) with RBAC
- `python/api/mcp_gateway_pool.py` — Connection pool status and health check
- `python/api/mcp_gateway_discover.py` — MCP Registry search proxy and server install
- `python/api/mcp_gateway_catalog.py` — Docker MCP Catalog browse and install

**Agent Tool:**
- `python/tools/mcp_discover.py` — Agent-facing `mcp_discover` tool (search registry, list tools, search tools)
- `prompts/agent.system.tool.mcp_discover.md` — Prompt template for discovery tool

**WebUI:**
- `webui/components/settings/mcp/gateway/mcp-gateway.html` — Gateway management UI (servers, discover, Docker catalog tabs)
- `webui/components/settings/mcp/gateway/mcp-gateway-store.js` — Alpine.js store for gateway state

**Coexistence:** MCPConfig (agent-side, settings-driven) and McpResourceStore (gateway-side, RBAC-driven) are independent systems that coexist. MCPConfig manages servers the agent connects to; McpResourceStore manages servers the gateway exposes to external clients.

## Gotchas

- **faiss-cpu pinned at 1.11.0** — do not upgrade until 1.15.0 (SWIG 4.4 + numpy.distutils fix)
- **faiss monkey patch**: `python/helpers/faiss_monkey_patch.py` — side-effect import in `memory.py`/`vector_db.py`, needed for Python 3.12/ARM
- **openai version override**: `[tool.uv] override-dependencies = ["openai==1.99.5"]` — browser-use pins 1.99.2
- **requirements.txt**: Auto-generated — never edit manually; use `mise run deps:add`
- **SWIG/aiohttp warnings**: `SwigPyPacked/__module__` and `enable_cleanup_closed` appear at startup; harmless, fix expected in faiss 1.15.0 and upstream LiteLLM
