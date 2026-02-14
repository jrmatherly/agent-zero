# Apollos AI - Project Overview

## Purpose
Apollos AI is a personal, organic agentic AI framework that grows and learns with the user. It is a general-purpose AI assistant that uses the computer as a tool—writing code, executing terminal commands, browsing the web, managing memory, and cooperating with subordinate agent instances.

## Tech Stack
- **Language**: Python 3.12+ (backend), vanilla JS + Alpine.js (frontend)
- **Web Framework**: Flask (sync routes) + uvicorn (ASGI) + python-socketio (WebSocket)
- **LLM Integration**: LiteLLM (multi-provider), LangChain Core
- **Embeddings**: sentence-transformers (local default), FAISS (vector DB), LiteLLM (remote providers)
- **Browser Automation**: Playwright, browser-use
- **Search**: DuckDuckGo, SearXNG, Perplexity
- **Document Processing**: unstructured, pypdf, pymupdf, newspaper3k
- **MCP**: FastMCP 3.0 for server (>=3.0.0rc2), mcp SDK for client
- **Scheduling**: crontab
- **Docker**: Custom base image + DockerfileLocal for local dev
- **Testing**: pytest, pytest-asyncio, pytest-mock

## Development Tooling
- **Task runner**: mise (`mise.toml`, 93 tasks) — manages Python, uv, ruff, biome, git-cliff, pkl, hk
- **Package manager**: uv (`pyproject.toml` source of truth, `uv.lock` committed)
- **Python linter/formatter**: Ruff (configured in `pyproject.toml`)
- **CSS/JS linter**: Biome (configured in `biome.json`)
- **Git hooks**: hk (`hk.pkl`) — pre-commit (ruff, biome, security, hygiene), commit-msg (conventional commits)
- **Changelog**: git-cliff (`cliff.toml`) — conventional commit parsing, Keep a Changelog format
- **Codebase analysis**: DriftDetect (`driftdetect@0.9.48`) — pattern scanning, Python analysis, Cortex memory, quality gates
- **CI/CD**: GitHub Actions (9 workflows: ci, claude, claude-code-review, drift, release, docker-base, hooks-check, codeql, dependency-review) + Dependabot (uv + github-actions + Docker base images)

## Architecture
- `agent.py` — Core Agent and AgentContext classes
- `models.py` — LLM model configuration using LiteLLM
- `initialize.py` — Agent initialization and config management
- `run_ui.py` — Flask/uvicorn web server entry point
- `python/tools/` — 19 agent tools (code execution, memory, search, browser, etc.)
- `python/helpers/` — 103 utility modules (files, docker, SSH, memory, MCP gateway, branding, auth, vault, tenant, RBAC, etc.)
- `python/api/` — 85 REST API endpoint handlers (auto-discovered from folder)
- `python/websocket_handlers/` — 4 WebSocket event handlers (namespace-based discovery)
- `python/extensions/` — 41 extensions across 24 lifecycle hook points
- `prompts/` — 102 system prompts and message templates (99 Markdown + 3 Python)
- `webui/` — Frontend HTML/CSS/JS (Alpine.js + vanilla JS)
- `knowledge/` — Knowledge base files for RAG
- `skills/` — SKILL.md standard skills (portable agent capabilities)
- `tests/` — 49 pytest test files
- `docker/` — Docker build scripts (base image + run scripts)
- `docs/` — 24 documentation files (includes reference/environment-variables.md)
- `conf/` — Runtime configuration (model_providers.yaml)
- `docs/reference/` — Reference documentation (environment-variables.md)
- `.drift/` — DriftDetect analysis artifacts (patterns, indexes, views, audit)
- `.github/workflows/` — CI/CD workflows

## Key Design Patterns
- **Extension system**: Lifecycle hooks in `python/extensions/` directories (e.g., `message_loop_start`, `tool_execute_before`)
- **Auto-discovery**: Tools, API handlers, and WebSocket handlers are auto-loaded from their folders
- **Multi-agent**: Agents can spawn subordinate agents; the first agent's superior is the human user
- **Memory**: Persistent vector-DB-based memory with FAISS (configurable embeddings: local or remote via LiteLLM)
- **Branding**: Centralized `python/helpers/branding.py` with 5 env vars (BRAND_NAME, BRAND_SLUG, BRAND_URL, BRAND_GITHUB_URL, BRAND_UPDATE_CHECK_URL); frontend Alpine.js store; prompt `{{brand_name}}` injection
- **Prompt-driven**: Behavior is defined by prompts in `prompts/` folder, fully customizable

## Authentication System (Phase 0+1)
- **Auth database**: SQLAlchemy + Alembic (`auth_db.py`, `user_store.py`, `alembic/versions/001_initial_schema.py`)
  - 8 tables: organizations, teams, users, org_memberships, team_memberships, chat_ownership, api_key_vault, entra_group_mappings
  - Default: SQLite at `usr/auth.db`; supports PostgreSQL for production
- **Encryption**: AES-256-GCM via `vault_crypto.py` with HKDF-derived keys from `VAULT_MASTER_KEY`
- **EntraID OIDC SSO**: MSAL confidential client auth-code flow (`auth.py` AuthManager)
  - PersistentTokenCache encrypted at rest via vault_crypto
  - Group overage handling (>200 groups → Graph API pagination)
- **Local login**: Username/password fallback via `user_store.verify_password()` (Argon2id)
- **Legacy compat**: AUTH_LOGIN/AUTH_PASSWORD still works; session["authentication"] key preserved
- **Session structure**: `session["user"] = {id, email, name, auth_method}`, `session["authentication"] = True`
- **Bootstrap**: `auth_bootstrap.py` runs Alembic migrations + creates admin from `ADMIN_EMAIL`/`ADMIN_PASSWORD`
- **Dual login UI**: `webui/login.html` shows SSO button (if OIDC configured) + local form
- **Routes**: `/login` (GET/POST), `/login/entra`, `/auth/callback`, `/logout`

## GitHub
- **Remote**: `jrmatherly/apollos-ai` (fork of `agent0ai/agent-zero`)
- **Container Registry**: GHCR (`ghcr.io/jrmatherly/apollos-ai`, `ghcr.io/jrmatherly/apollos-ai-base`)
- **CI/CD Workflows**:
  - `ci.yml` — Lint + format + test (parallel jobs); paths-ignore, concurrency, uv cache
  - `drift.yml` — Codebase pattern analysis (push to main, manual dispatch, weekly)
  - `release.yml` — git-cliff changelog + GitHub release on `v*` tag push
  - `hooks-check.yml` — hk pre-commit validation on PRs
  - `codeql.yml` — CodeQL security analysis (Python) on push/PR + weekly
  - `dependency-review.yml` — Dependency review + requirements.txt sync on PRs
  - `dependabot.yml` — Weekly uv + GitHub Actions dependency updates
  - Issue templates (YAML forms), PR template
