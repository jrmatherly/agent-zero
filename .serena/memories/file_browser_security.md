# File Browser Security Analysis

## Critical Finding (2026-02-13)
`FileBrowser.__init__` hardcodes `base_dir = "/"` (line 29 of `python/helpers/file_browser.py`), granting full container filesystem access through the web UI. All 7 file browser API endpoints are affected.

## Affected Endpoints
- `/get_work_dir_files`, `/delete_work_dir_file`, `/rename_work_dir_file`
- `/upload_work_dir_files`, `/edit_work_dir_file`, `/download_work_dir_file`, `/file_info`

## Key Insight
`TenantContext` already has a `workdir` property (`usr/orgs/{org}/teams/{team}/members/{user}/workdir`) and `ensure_dirs()` exists but doesn't create the workdir. The fix is to wire TenantContext into FileBrowser.

## Implementation Plan
Documented in `.scratchpad/file-browser-workspace-isolation.md` with 6 phases:
1. Make FileBrowser accept `base_dir` parameter
2. Wire TenantContext into all 7 API handlers
3. Add workdir to `ensure_dirs()`
4. Fix `$WORK_DIR` sentinel resolution
5. Frontend path display (minimal changes needed)
6. Security tests

## Good Pattern to Follow
`python/api/upload.py` already uses `self._get_tenant_ctx()` for per-user upload paths — same pattern for file browser.
