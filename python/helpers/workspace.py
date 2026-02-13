"""Workspace resolution helpers for per-user file browser isolation."""

from python.helpers import files
from python.helpers.tenant import TenantContext

BASELINE_DIR = "usr/baseline"


def get_workspace_root(tenant_ctx: TenantContext) -> str:
    """Resolve absolute workspace path for the current user."""
    if tenant_ctx.is_system:
        return files.get_abs_path("usr/workdir")
    return files.get_abs_path(tenant_ctx.workdir)


def get_baseline_root() -> str:
    """Resolve absolute path to admin-managed baseline directory."""
    return files.get_abs_path(BASELINE_DIR)


def get_team_shared_root(tenant_ctx: TenantContext) -> str:
    """Resolve absolute path to team shared workspace."""
    if tenant_ctx.is_system:
        return files.get_abs_path("usr/shared")
    return files.get_abs_path(f"{tenant_ctx.team_dir}/shared")


def resolve_virtual_path(
    current_path: str, workspace: str, baseline_dir: str, shared_dir: str
) -> tuple[str, str, bool]:
    """Resolve virtual path prefixes to actual directories.

    Returns (resolved_base_dir, relative_sub_path, is_readonly).
    """
    if current_path.startswith("$BASELINE/"):
        sub_path = current_path[len("$BASELINE/") :]
        return baseline_dir, sub_path, True
    elif current_path == "$BASELINE":
        return baseline_dir, "", True
    elif current_path.startswith("$SHARED/"):
        sub_path = current_path[len("$SHARED/") :]
        return shared_dir, sub_path, False
    elif current_path == "$SHARED":
        return shared_dir, "", False
    else:
        return workspace, current_path, False


def is_admin_user(tenant_ctx: TenantContext) -> bool:
    """Check if user has admin workspace access (RBAC integration point)."""
    # TODO: Wire to actual RBAC check via casbin
    return False
