# AGENTS.md

Cross-framework agent instructions for Apollos AI. This file complements CLAUDE.md with a format understood by multiple AI coding agents.

## Project

Apollos AI is a personal organic agentic AI framework (Python backend, Alpine.js frontend). Fork of `agent0ai/agent-zero`.

## Build and Test

```bash
# All commands use mise task runner
mise run setup           # First-time setup
mise run r               # Start UI server
mise run t               # Run tests (pytest)
mise run lint            # Lint (Ruff + Biome)
mise run ci              # Full CI: lint + format check + test

# Single test file
mise run t -- tests/test_example.py -v

# Add a dependency
mise run deps:add <package>
```

Do NOT invoke `uv run`, `pytest`, `ruff`, or `docker compose` directly. Always use `mise run <task>`.

## Code Style

- Python: `snake_case` functions, `PascalCase` classes, `str | None` unions (not `Optional`)
- Commits: Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`)
- Pre-commit hooks enforce Ruff lint/format, Biome CSS, and conventional commit messages

## Architecture

- Entry point: `run_ui.py` (Flask + uvicorn + python-socketio)
- Agent loop: `agent.py` — prompt -> LLM -> parse JSON -> execute tool -> repeat
- Auto-discovery: Drop files in `python/tools/`, `python/api/`, or `python/websocket_handlers/` and they activate automatically
- Extensions: `python/extensions/<hook_name>/` with filename-prefix sorting (`_10_`, `_20_`)
- Settings: `python/helpers/settings.py` TypedDict with `A0_SET_` env var overrides
- MCP Gateway: `python/helpers/mcp_gateway_*.py` — multi-server composition, discovery, and lifecycle management; APIs in `python/api/mcp_gateway_*.py`; agent tool `mcp_discover`

## Key Patterns

**New API endpoint:** Extend `ApiHandler` in `python/api/`, implement `async process(input, request) -> dict`.

**New tool:** Extend `Tool` in `python/tools/`, implement `async execute(**kwargs) -> Response`.

**New extension:** Extend `Extension` in `python/extensions/<hook>/`, prefix-sorted filename.

## Testing

- Framework: pytest + pytest-asyncio (async auto-detection)
- Run: `mise run t` or `mise run t -- tests/test_file.py -v`
- Async tests: Just use `async def test_...` — no decorator needed

## Dependencies

- Source of truth: `pyproject.toml` (managed by uv)
- Never edit `requirements.txt` manually (auto-generated)
- Add deps: `mise run deps:add <package>`

## Security

- Secrets in `usr/.env` (gitignored)
- Vault encryption: AES-256-GCM via `vault_crypto.py`
- Auth: OIDC (Entra ID) + local Argon2id fallback
- Webhook verification: HMAC-SHA256 (GitHub, Slack) and shared secret (Jira)

## Gotchas

- faiss-cpu pinned at 1.11.0 — do not upgrade until 1.15.0
- openai version override in `[tool.uv]` section of pyproject.toml
- Docker base image uses dash (not bash) — use POSIX shell syntax
