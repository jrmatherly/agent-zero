from __future__ import annotations

import os
from dataclasses import dataclass

from python.helpers import files

SYSTEM_USER_ID = "system"
DEFAULT_ORG_ID = "default"
DEFAULT_TEAM_ID = "default"


@dataclass(frozen=True)
class TenantContext:
    """Resolves all filesystem paths for a user's position in the org/team/user hierarchy.

    Every authenticated user gets paths under:
        usr/orgs/{org_id}/teams/{team_id}/members/{user_id}/

    The full org/team hierarchy is architecturally present but all users share
    "default"/"default" until Phase 4 adds real org/team management.
    No-auth mode uses user_id="system".
    """

    user_id: str
    org_id: str = DEFAULT_ORG_ID
    team_id: str = DEFAULT_TEAM_ID

    # -- Factory methods -------------------------------------------------------

    @classmethod
    def from_session_user(cls, user: dict | None) -> TenantContext:
        """Build TenantContext from the session["user"] dict (or None for no-auth)."""
        if not user:
            return cls.system()
        user_id = str(user.get("id", SYSTEM_USER_ID))
        org_id = str(user.get("org_id", DEFAULT_ORG_ID))
        team_id = str(user.get("team_id", DEFAULT_TEAM_ID))
        return cls(user_id=user_id, org_id=org_id, team_id=team_id)

    @classmethod
    def system(cls) -> TenantContext:
        """Return a TenantContext for system/no-auth mode."""
        return cls(
            user_id=SYSTEM_USER_ID, org_id=DEFAULT_ORG_ID, team_id=DEFAULT_TEAM_ID
        )

    # -- Path properties -------------------------------------------------------

    @property
    def is_system(self) -> bool:
        return self.user_id == SYSTEM_USER_ID

    @property
    def user_dir(self) -> str:
        """Relative path to the user's data root (e.g. usr/orgs/default/teams/default/members/{user_id})."""
        return f"usr/orgs/{self.org_id}/teams/{self.team_id}/members/{self.user_id}"

    @property
    def team_dir(self) -> str:
        return f"usr/orgs/{self.org_id}/teams/{self.team_id}"

    @property
    def org_dir(self) -> str:
        return f"usr/orgs/{self.org_id}"

    @property
    def chats_dir(self) -> str:
        return f"{self.user_dir}/chats"

    @property
    def memory_subdir(self) -> str:
        """User's private FAISS memory subdir (relative, used as key in Memory.index)."""
        return f"orgs/{self.org_id}/teams/{self.team_id}/members/{self.user_id}/default"

    @property
    def settings_file(self) -> str:
        """Relative path to the user's settings override file."""
        return f"{self.user_dir}/settings.json"

    @property
    def secrets_file(self) -> str:
        """Relative path to the user's encrypted secrets file."""
        return f"{self.user_dir}/secrets.env"

    @property
    def uploads_dir(self) -> str:
        return f"{self.user_dir}/uploads"

    @property
    def workdir(self) -> str:
        return f"{self.user_dir}/workdir"

    # -- Directory creation ----------------------------------------------------

    def ensure_dirs(self) -> None:
        """Lazily create the user's directory tree on first use."""
        dirs = [
            self.chats_dir,
            self.uploads_dir,
            self.workdir,
        ]
        for d in dirs:
            abs_path = files.get_abs_path(d)
            os.makedirs(abs_path, exist_ok=True)
