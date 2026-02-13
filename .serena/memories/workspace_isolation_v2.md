# Workspace Isolation — Research & Design Summary (v2)

## Status
Researched & Designed — awaiting implementation. Full plan at `.scratchpad/file-browser-workspace-isolation.md` (v2.0).

## Core Vulnerability
`FileBrowser.__init__` hardcodes `base_dir="/"` — all 7 file browser API endpoints allow full container FS access (CWE-22/CWE-552).

## Finalized Decisions
1. **Team workspace**: Both per-user AND shared team workspace
2. **Admin scope**: App root `/a0` only (never full container `/`), requires RBAC check
3. **Baseline model**: Live overlay — admin baseline read-only, merged view with badges, auto-propagation
4. **Agent scope**: Agent code_execution also constrained to user's workspace boundary

## Key Architecture
- `TenantContext.workdir` already exists but isn't wired to FileBrowser
- `ensure_dirs()` missing workdir creation
- `upload.py` demonstrates correct tenant-aware pattern to follow
- New `python/helpers/workspace.py` module for workspace resolution
- Baseline at `/a0/usr/baseline/` (read-only overlay)
- Team shared at `/a0/usr/orgs/{org}/teams/{team}/shared/`

## 8-Phase Implementation Plan
1. FileBrowser accepts `base_dir` parameter
2. Wire TenantContext into 7 API handlers
3. Workspace auto-creation in `ensure_dirs()`
4. Fix `$WORK_DIR` sentinel (currently resolves to `/a0`)
5. Baseline overlay merged file listing
6. Agent execution confinement (code_execution, shell_ssh, shell_local)
7. Frontend badges for baseline/shared items
8. Tests (17 test cases)

## Research Sources
- **aionui**: DirectoryService (DB-backed, chain resolution user→team→org→global), MiseEnvironmentService
- **uv**: `UV_PROJECT_ENVIRONMENT`, `UV_CACHE_DIR` per-user isolation, thread-safe cache
- **mise**: `MISE_DATA_DIR/CONFIG_DIR/CACHE_DIR/STATE_DIR` per-user, XDG compliance, monorepo support
- **2026 best practices**: OverlayFS, nsjail/bubblewrap, E2B/Firecracker, Microsandbox (libkrun), Snekbox
