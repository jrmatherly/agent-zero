# Contributing to Apollos AI

Contributions to improve Apollos AI are very welcome! This guide outlines how to contribute code, documentation, or other improvements.

## Prerequisites

Before you begin, make sure you have the following tools installed:

| Tool | Purpose |
|------|---------|
| **[mise](https://mise.jdx.dev/)** | Task runner and tool manager. **All commands must use `mise run <task>`** — never invoke tools like `uv`, `pytest`, or `ruff` directly. |
| **[uv](https://docs.astral.sh/uv/)** | Python package manager (managed by mise). Do not use `pip`. |
| **Python 3.12** | Runtime (managed by mise — installed automatically). |
| **[Docker](https://www.docker.com/)** | For building and running the runtime container. |
| **Git** | Version control. |

> **Tip:** Once mise is installed, running `mise install` in the project root will automatically set up Python, uv, and the other managed tools for you.

## Getting Started

- See [development](../setup/dev-setup.md) for detailed instructions on setting up a development environment.
- See [extensions](../developer/extensions.md) for instructions on how to create custom extensions.
- See [websocket infrastructure](../developer/websockets.md) for guidance on building real-time handlers and client integrations.

1. **Fork the Repository:** Fork the Apollos AI repository on GitHub.
2. **Clone Your Fork:** Clone your forked repository to your local machine.
3. **Create a Branch:** Create a new branch for your changes. Use a descriptive name that reflects the purpose of your contribution (e.g., `fix-memory-leak`, `add-search-tool`, `improve-docs`).

## First-Time Setup

After cloning the repository, run the canonical setup command:

```bash
git clone https://github.com/jrmatherly/apollos-ai
cd apollos-ai

# One-command setup: installs dependencies, Playwright browser, and git hooks
mise run setup

# Create your local environment config
cp usr/.env.example usr/.env
# Edit usr/.env with your API keys and settings

# Verify everything works
mise run t
```

The `mise run setup` command handles everything:
- Creates a Python virtual environment
- Installs all project dependencies (including dev tools)
- Installs Playwright's Chromium browser (used for browser-use features)
- Installs git hooks via **hk** (pre-commit and commit-msg hooks)

## Development Workflow

All tooling is managed by **mise**. Here are the commands you will use most often:

| Command | Description |
|---------|-------------|
| `mise run r` | Start the UI server (alias for `run`) |
| `mise run t` | Run tests (alias for `test`) |
| `mise run lint` | Lint all code (Ruff for Python + Biome for CSS) |
| `mise run lint:python` | Lint Python code only |
| `mise run lint:css` | Lint CSS files only |
| `mise run format` | Auto-format all code |
| `mise run format:check` | Check formatting without writing (CI mode) |
| `mise run ci` | Full CI suite: lint + format check + test |
| `mise run hooks:check` | Run pre-commit checks manually |
| `mise run hooks:fix` | Run pre-commit fixes (auto-fix what can be fixed) |
| `mise run info` | Show project info and tool versions |

To run a single test file:

```bash
mise run t -- tests/test_websocket_manager.py
```

> **Important:** Never run `uv run`, `pytest`, `ruff`, `biome`, or other tools directly. Always use the corresponding `mise run` task. This ensures consistent tool versions and configuration across all contributors.

## Code Style

### Python

- **Functions and variables:** `snake_case`
- **Classes:** `PascalCase`
- **Type unions:** Use `str | None` (not `Optional[str]`)
- **Linter:** [Ruff](https://docs.astral.sh/ruff/) — enforced via pre-commit hooks
- **Formatter:** Ruff format — enforced via pre-commit hooks

### CSS

- **Linter:** [Biome](https://biomejs.dev/) — enforced via pre-commit hooks
- Scope: all files under `webui/css/` (excluding `webui/vendor/`)

### General

- Follow the existing code style in whatever file or module you are editing.
- Update documentation if your changes affect user-facing functionality. Documentation is written in Markdown.
- **Never invoke tools directly** — always use `mise run` tasks (e.g., `mise run lint`, not `ruff check`).

## Commit Messages

Apollos AI enforces **[Conventional Commits](https://www.conventionalcommits.org/)** via a `commit-msg` hook managed by **hk**.

### Format

```text
type(scope): description
```

The `(scope)` is optional. The `description` should be a concise summary in imperative mood (e.g., "add feature" not "added feature").

### Allowed Types

| Type | When to Use |
|------|-------------|
| `feat` | A new feature |
| `fix` | A bug fix |
| `refactor` | Code restructuring (no new feature or bug fix) |
| `docs` | Documentation-only changes |
| `style` | Formatting, whitespace, missing semicolons (no logic change) |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `chore` | Build process, tooling, dependency updates |
| `ci` | CI/CD configuration changes |
| `security` | Security-related fixes or improvements |

### Examples

```text
feat: add new search tool for knowledge base
fix: resolve memory leak in agent monologue loop
refactor(api): extract common validation into middleware
docs: update contribution guide with commit conventions
test: add coverage for websocket reconnection
chore: bump ruff to latest version
ci: add CodeQL security scanning workflow
security: sanitize user input in code execution tool
```

### What Happens If You Get It Wrong

Commits that do not follow this format will be **rejected** by the `commit-msg` hook. You will see an error and the commit will not be created. Simply amend your commit message to match the required format and try again.

## Pre-commit Hooks

Pre-commit hooks run automatically on every commit. They are managed by **[hk](https://github.com/jdx/hk)** and installed during `mise run setup`.

### What Gets Checked

The pre-commit hook runs the following checks on staged files:

**Security:**
- Private key detection — prevents accidentally committing secrets
- Large file detection — blocks files over 500 KB
- Merge conflict marker detection — catches unresolved conflicts

**Hygiene:**
- Trailing whitespace removal (auto-fixed; excludes `.md` files)
- End-of-file newline enforcement (auto-fixed)

**Linters:**
- Ruff linting — Python code quality (`**/*.py`, excludes `.venv/`, `__pycache__/`, `*._py`)
- Ruff formatting — Python code formatting
- Biome linting — CSS code quality (`webui/**/*.css`, excludes `webui/vendor/`)

### Running Hooks Manually

You can run the full pre-commit check suite at any time without committing:

```bash
mise run hooks:check    # Check only (no auto-fix)
mise run hooks:fix      # Check and auto-fix where possible
```

### If a Hook Fails

Fix the issue reported, re-stage your files, and commit again. The hooks use `fail_fast = true`, so they stop at the first failure to keep feedback focused.

## Adding Dependencies

Dependencies are managed by **uv** with `pyproject.toml` as the source of truth. The `requirements.txt` file is auto-generated for Docker compatibility.

```bash
# Add a production dependency
mise run deps:add <package>

# Add a dev-only dependency
mise run deps:add-dev <package>
```

The `deps:add` task automatically:
1. Adds the package to `pyproject.toml`
2. Regenerates `requirements.txt` from the lock file

> **Never edit `requirements.txt` manually.** It is auto-generated and will be overwritten. If you need to regenerate it from the current lock file, run `mise run deps:export`.

## Naming Conventions

### Files

- Files ending in `._py` are **disabled/archived** — do not modify these unless you are intentionally reactivating them.
- Extension files are sorted by filename prefix (e.g., `_10_`, `_20_`). This determines execution order.

### Adding New Components

When contributing new tools, API endpoints, extensions, or WebSocket handlers, follow these patterns:

| Component | Base Class | Key Method | Directory |
|-----------|-----------|------------|-----------|
| **Tool** | `Tool` | `async execute(**kwargs) -> Response` | `python/tools/` |
| **API handler** | `ApiHandler` | `async process(input, request) -> dict` | `python/api/` |
| **Extension** | `Extension` | `async execute(**kwargs)` | `python/extensions/<hook>/` |
| **WebSocket handler** | (namespace-based) | Auto-discovered | `python/websocket_handlers/` |

All of these follow the **auto-discovery pattern**: drop a file into the correct directory and it is automatically loaded at startup. No registration boilerplate required.

For extensions, the filename prefix determines sort order (e.g., `_10_my_extension.py` runs before `_20_another.py`). User overrides go in `usr/extensions/` with the same filename.

## Making Changes

- Follow the code style and naming conventions described above.
- Update documentation if your changes affect user-facing functionality.
- Write or update tests for any new or changed behavior. Tests live in the `tests/` directory and use `pytest-asyncio` with `asyncio_mode = "auto"` (async test functions are auto-detected).
- Run `mise run ci` before opening a pull request to catch issues early.

## Pull Request Guidelines

1. **Push Your Branch:** Push your branch to your forked repository on GitHub.
2. **Create a Pull Request:** Create a pull request targeting the `main` branch of the main repository.
3. **Follow the PR Template:** A pull request template is provided at `.github/pull_request_template.md`. It includes a checklist — please complete it. The template covers:
   - Description of the change
   - Related issues
   - Type of change (bug fix, feature, breaking change, docs, refactor)
   - Testing confirmation (`mise run test`, `mise run lint`, local testing)
4. **CI Will Run Automatically:** The CI pipeline includes multiple GitHub Actions workflows that will check your pull request:
   - **ci.yml** — Lint + format check + test (parallel jobs)
   - **hooks-check.yml** — hk hook validation
   - **codeql.yml** — CodeQL security analysis (Python)
   - **dependency-review.yml** — Dependency vulnerability review + requirements.txt sync check
   - Additional workflows run for Docker and release changes as needed
5. **Ensure CI Passes Locally First:** Run `mise run ci` before opening your PR. This runs the same lint, format, and test checks that CI will run.
6. **Address Feedback:** Be responsive to feedback from the community. We love contributions, and we also love to discuss them!

## Docker (Optional)

If your changes affect the Docker runtime or you want to test in a container:

```bash
mise run docker:build:local    # Build local dev image from working tree
mise run docker:run            # Run local container (port 50080 -> 80)
```

See the [mise.toml](../../mise.toml) file for the full list of Docker-related tasks.

## Documentation

The documentation is written in Markdown and lives in the `docs/` directory. We appreciate contributions to documentation — even small fixes like typos or clarifications are valuable. If you are adding a new feature, please include corresponding documentation updates in the same pull request.

## Getting Help

If you have questions or need help with your contribution:

- Open a [GitHub Issue](https://github.com/jrmatherly/apollos-ai/issues) using one of the provided templates (bug report or feature request)
- Check existing issues and discussions for context on ongoing work

Thank you for contributing to Apollos AI!
