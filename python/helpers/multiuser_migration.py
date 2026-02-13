"""Idempotent migration from single-user to multi-user directory layout.

Moves legacy global data into the system user's tenant directory.
Called once from initialize_migration() when usr/orgs/ doesn't exist.
"""

import json
import os
import shutil

from python.helpers import files
from python.helpers.print_style import PrintStyle
from python.helpers.tenant import SYSTEM_USER_ID, TenantContext

# Legacy paths (pre-Phase 2)
LEGACY_CHATS = "usr/chats"
LEGACY_MEMORY = "usr/memory"
LEGACY_SETTINGS = "usr/settings.json"
LEGACY_SECRETS = "usr/secrets.env"
LEGACY_UPLOADS = "usr/uploads"

# Global settings path (shared across all users)
GLOBAL_SETTINGS = "usr/global/settings.json"


def migrate_to_multiuser() -> None:
    """Run idempotent migration from single-user to multi-user layout.

    Safe to call multiple times — checks for usr/orgs/ existence first.
    """
    orgs_dir = files.get_abs_path("usr/orgs")
    if os.path.isdir(orgs_dir):
        PrintStyle.step("Multi-user", "already configured", last=True)
        return

    PrintStyle.step("Multi-user", "migrating...")

    system_ctx = TenantContext.system()

    # 1. Promote usr/settings.json → usr/global/settings.json
    _migrate_global_settings()

    # 2. Create system user directory tree
    system_ctx.ensure_dirs()

    # 3. Move legacy chats to system user's chats dir
    _migrate_chats(system_ctx)

    # 4. Move legacy memory to system user's memory dir
    _migrate_memory(system_ctx)

    # 5. Copy legacy secrets to system user's secrets file
    _migrate_secrets(system_ctx)

    # 6. Move legacy uploads to system user's uploads dir
    _migrate_uploads(system_ctx)

    PrintStyle.step("Multi-user", "complete", last=True)


def _migrate_global_settings() -> None:
    """Copy usr/settings.json → usr/global/settings.json (if not already done)."""
    src = files.get_abs_path(LEGACY_SETTINGS)
    dst = files.get_abs_path(GLOBAL_SETTINGS)

    if os.path.isfile(src) and not os.path.isfile(dst):
        PrintStyle().print(f"  Promoting {LEGACY_SETTINGS} → {GLOBAL_SETTINGS}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _migrate_chats(system_ctx: TenantContext) -> None:
    """Move usr/chats/{ctxid}/ → system user chats dir, patching user_id."""
    src_dir = files.get_abs_path(LEGACY_CHATS)
    dst_dir = files.get_abs_path(system_ctx.chats_dir)

    if not os.path.isdir(src_dir):
        return

    os.makedirs(dst_dir, exist_ok=True)

    for ctx_folder in os.listdir(src_dir):
        src_ctx = os.path.join(src_dir, ctx_folder)
        if not os.path.isdir(src_ctx):
            continue

        dst_ctx = os.path.join(dst_dir, ctx_folder)
        if os.path.exists(dst_ctx):
            continue  # Already migrated

        # Patch chat.json to include user_id
        chat_json = os.path.join(src_ctx, "chat.json")
        if os.path.isfile(chat_json):
            try:
                with open(chat_json) as f:
                    data = json.load(f)
                if "user_id" not in data or not data["user_id"]:
                    data["user_id"] = SYSTEM_USER_ID
                    with open(chat_json, "w") as f:
                        json.dump(data, f, ensure_ascii=False)
            except (json.JSONDecodeError, OSError):
                pass  # Skip corrupt files

        shutil.move(src_ctx, dst_ctx)
        PrintStyle().print(f"  Migrated chat {ctx_folder}")


def _migrate_memory(system_ctx: TenantContext) -> None:
    """Move usr/memory/default/ → system user memory dir."""
    src_dir = files.get_abs_path("usr/memory/default")
    dst_dir = files.get_abs_path("usr", system_ctx.memory_subdir, "memory")

    if not os.path.isdir(src_dir):
        return
    if os.path.isdir(dst_dir):
        return  # Already migrated

    os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
    shutil.move(src_dir, dst_dir)
    PrintStyle().print("  Migrated default memory to system user")


def _migrate_secrets(system_ctx: TenantContext) -> None:
    """Copy usr/secrets.env → system user secrets file."""
    src = files.get_abs_path(LEGACY_SECRETS)
    dst = files.get_abs_path(system_ctx.secrets_file)

    if not os.path.isfile(src):
        return
    if os.path.isfile(dst):
        return  # Already migrated

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    PrintStyle().print("  Copied secrets to system user")


def _migrate_uploads(system_ctx: TenantContext) -> None:
    """Move usr/uploads/ → system user uploads dir."""
    src_dir = files.get_abs_path(LEGACY_UPLOADS)
    dst_dir = files.get_abs_path(system_ctx.uploads_dir)

    if not os.path.isdir(src_dir):
        return
    if os.path.isdir(dst_dir):
        return  # Already migrated

    os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
    shutil.move(src_dir, dst_dir)
    PrintStyle().print("  Migrated uploads to system user")
