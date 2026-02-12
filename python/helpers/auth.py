"""AuthManager — EntraID OIDC SSO + local fallback authentication.

Wraps MSAL ``ConfidentialClientApplication`` for the authorization-code flow
and provides a local username/password fallback using the ``user_store``
module.  Includes ``PersistentTokenCache`` for encrypted MSAL token cache
persistence across process restarts.

Configuration (env vars or Flask app.config):
    OIDC_TENANT_ID   — Microsoft Entra tenant ID
    OIDC_CLIENT_ID   — App registration client ID
    OIDC_CLIENT_SECRET — App registration client secret
    OIDC_REDIRECT_URI  — (optional) Explicit callback URL
"""

import os
import secrets

import msal
from flask import Flask, session, url_for

from python.helpers import auth_db, files, user_store, vault_crypto
from python.helpers.print_style import PrintStyle

# ---------------------------------------------------------------------------
# Persistent MSAL Token Cache (AES-256-GCM encrypted via vault_crypto)
# ---------------------------------------------------------------------------

_CACHE_FILE = "usr/auth_token_cache.bin"


class PersistentTokenCache:
    """MSAL token cache that persists encrypted to disk.

    Uses ``vault_crypto`` with purpose ``"msal_token_cache"`` so the cache
    file is encrypted at rest with an HKDF-derived key independent of the
    API key vault.
    """

    def __init__(self) -> None:
        self.cache = msal.SerializableTokenCache()
        self._load()

    def _load(self) -> None:
        cache_path = files.get_abs_path(_CACHE_FILE)
        if os.path.exists(cache_path):
            try:
                encrypted = files.read_file(cache_path)
                decrypted = vault_crypto.decrypt(encrypted, purpose="msal_token_cache")
                self.cache.deserialize(decrypted)
            except Exception:
                PrintStyle.warning(
                    "MSAL token cache corrupted or key changed — starting fresh"
                )

    def save(self) -> None:
        if self.cache.has_state_changed:
            serialized = self.cache.serialize()
            encrypted = vault_crypto.encrypt(serialized, purpose="msal_token_cache")
            files.write_file(files.get_abs_path(_CACHE_FILE), encrypted)

    def get_cache(self) -> msal.SerializableTokenCache:
        return self.cache


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------


class AuthManager:
    """Manages EntraID OIDC and local authentication for the web UI.

    Instantiate once during app startup. If OIDC env vars are not set the
    manager operates in local-only mode and ``is_oidc_configured`` returns
    ``False``.
    """

    def __init__(self, app: Flask) -> None:
        self.client_id: str = os.environ.get("OIDC_CLIENT_ID", "")
        self.client_secret: str = os.environ.get("OIDC_CLIENT_SECRET", "")
        self.tenant_id: str = os.environ.get("OIDC_TENANT_ID", "")
        self.redirect_uri: str = os.environ.get("OIDC_REDIRECT_URI", "")
        self.scopes: list[str] = ["User.Read"]

        self._token_cache: PersistentTokenCache | None = None

        if self.is_oidc_configured:
            self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            try:
                self._token_cache = PersistentTokenCache()
                PrintStyle.info("AuthManager: EntraID OIDC configured")
            except RuntimeError:
                PrintStyle.warning(
                    "AuthManager: VAULT_MASTER_KEY not set — OIDC token cache disabled"
                )
        else:
            self.authority = ""
            PrintStyle.info("AuthManager: OIDC not configured — local-only mode")

    @property
    def is_oidc_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.tenant_id)

    def _build_msal_app(self) -> msal.ConfidentialClientApplication:
        cache = self._token_cache.get_cache() if self._token_cache else None
        return msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=cache,
        )

    # ---- OIDC flow ---------------------------------------------------------

    def get_login_url(self) -> str:
        """Generate the OIDC authorization URL and stash the flow in session."""
        app = self._build_msal_app()
        redirect_uri = self.redirect_uri or url_for("auth_callback", _external=True)
        flow = app.initiate_auth_code_flow(
            scopes=self.scopes,
            redirect_uri=redirect_uri,
        )
        session["auth_flow"] = flow
        return flow["auth_uri"]

    def process_callback(self, request_args: dict) -> dict:
        """Exchange the authorization code for tokens and extract user info.

        Args:
            request_args: The ``request.args`` from the callback request.

        Returns:
            A dict with keys: sub, email, name, groups, roles, auth_method.

        Raises:
            ValueError: If the token exchange fails.
        """
        app = self._build_msal_app()
        flow = session.pop("auth_flow", {})
        result = app.acquire_token_by_auth_code_flow(flow, request_args)

        if "error" in result:
            desc = result.get("error_description", result["error"])
            raise ValueError(f"OIDC authentication failed: {desc}")

        if self._token_cache:
            self._token_cache.save()

        claims = result.get("id_token_claims", {})
        access_token = result.get("access_token", "")
        groups = self._resolve_groups(claims, access_token)

        return {
            "sub": claims.get("oid") or claims.get("sub"),
            "email": claims.get("preferred_username") or claims.get("email"),
            "name": claims.get("name"),
            "groups": groups,
            "roles": claims.get("roles", []),
            "auth_method": "entra",
        }

    def _resolve_groups(self, claims: dict, access_token: str) -> list[str]:
        """Extract groups from claims or fetch via Graph API on overage."""
        if "groups" in claims:
            return claims["groups"]

        # Group overage: >200 groups, need to fetch from Graph API
        if "_claim_names" in claims and "groups" in claims.get("_claim_names", {}):
            return self._fetch_groups_from_graph(access_token)

        return []

    @staticmethod
    def _fetch_groups_from_graph(access_token: str) -> list[str]:
        """Fetch user groups from Microsoft Graph API with pagination."""
        import httpx

        groups: list[str] = []
        url: str | None = (
            "https://graph.microsoft.com/v1.0/me/transitiveMemberOf?$select=id&$top=999"
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        while url:
            resp = httpx.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                PrintStyle.warning(f"Graph API group fetch failed: {resp.status_code}")
                break
            data = resp.json()
            groups.extend(m["id"] for m in data.get("value", []))
            url = data.get("@odata.nextLink")

        return groups

    # ---- Local login -------------------------------------------------------

    @staticmethod
    def login_local(email: str, password: str) -> dict | None:
        """Authenticate against the local user store.

        Returns:
            A userinfo dict on success, or ``None`` on failure.
        """
        with auth_db.get_session() as db:
            user = user_store.get_user_by_email(db, email)
            if not user or user.auth_provider != "local":
                return None
            if not user_store.verify_password(user, password):
                return None
            return {
                "sub": user.id,
                "email": user.email,
                "name": user.display_name,
                "groups": [],
                "roles": [],
                "auth_method": "local",
            }

    # ---- Session helpers ---------------------------------------------------

    @staticmethod
    def establish_session(userinfo: dict) -> None:
        """Create or update user in the DB and populate the Flask session."""
        with auth_db.get_session() as db:
            user = user_store.upsert_user(db, userinfo)
            if userinfo.get("groups"):
                user_store.sync_group_memberships(db, user, userinfo["groups"])

            # Auto-assign SSO users to default org/team when they have no
            # memberships (JIT-provisioned without EntraID group mappings).
            _auto_assign_default_memberships(db, user)

            # Capture user attributes for session before leaving DB context
            is_system_admin = bool(user.is_system_admin)
            # Resolve primary org/team from first membership
            org_id = "default"
            team_id = "default"
            if user.org_memberships:
                org_id = user.org_memberships[0].org_id
            else:
                PrintStyle.warning(f"User {user.id} has no org memberships")
            if user.team_memberships:
                tm = user.team_memberships[0]
                team_id = tm.team_id
            else:
                PrintStyle.warning(f"User {user.id} has no team memberships")

        # Sync Casbin RBAC roles for this user
        try:
            from python.helpers.rbac import sync_user_roles

            sync_user_roles(userinfo["sub"])
        except Exception as e:
            PrintStyle.warning(f"RBAC role sync skipped: {e}")

        # Prevent session fixation: clear stale pre-auth data before populating
        session.clear()
        session["csrf_token"] = secrets.token_urlsafe(32)
        session["user"] = {
            "id": userinfo["sub"],
            "email": userinfo["email"],
            "name": userinfo.get("name"),
            "auth_method": userinfo.get("auth_method", "entra"),
            "is_system_admin": is_system_admin,
            "org_id": org_id,
            "team_id": team_id,
        }
        # Backward compatibility — existing code checks session["authentication"]
        session["authentication"] = True
        session.permanent = True

    @staticmethod
    def clear_session() -> None:
        """Clear auth-related session keys."""
        session.pop("user", None)
        session.pop("authentication", None)
        session.pop("auth_flow", None)

    @staticmethod
    def get_current_user() -> dict | None:
        """Return the current user dict from session, or None."""
        return session.get("user")


# ---------------------------------------------------------------------------
# SSO auto-assignment helper
# ---------------------------------------------------------------------------


def _auto_assign_default_memberships(
    db: "Session",  # noqa: F821 — forward ref to sqlalchemy.orm.Session
    user: "user_store.User",
) -> None:
    """Auto-assign a user to the default org/team if they have no memberships.

    Controlled by env vars:
        ``A0_SET_SSO_AUTO_ASSIGN`` — ``"true"`` (default) to enable.
        ``A0_SET_SSO_DEFAULT_ROLE`` — Role to assign (default ``"member"``).

    This bridges the gap for JIT-provisioned SSO users who don't have
    EntraID group mappings configured.  When disabled, SSO users without
    group mappings will receive 403 until manually assigned by an admin.
    """
    if os.environ.get("A0_SET_SSO_AUTO_ASSIGN", "true").lower() != "true":
        return

    default_role = os.environ.get("A0_SET_SSO_DEFAULT_ROLE", "member")

    if not user.org_memberships:
        default_org = (
            db.query(user_store.Organization).filter_by(slug="default").first()
        )
        if default_org:
            org_mem = user_store.OrgMembership(
                user_id=user.id,
                org_id=default_org.id,
                role=default_role,
            )
            db.add(org_mem)
            db.flush()
            PrintStyle.info(
                f"Auto-assigned user {user.id} to default org as {default_role}"
            )

    if not user.team_memberships:
        default_team = db.query(user_store.Team).filter_by(slug="default").first()
        if default_team:
            team_mem = user_store.TeamMembership(
                user_id=user.id,
                team_id=default_team.id,
                role=default_role,
            )
            db.add(team_mem)
            db.flush()
            PrintStyle.info(
                f"Auto-assigned user {user.id} to default team as {default_role}"
            )

    # Refresh so relationships are visible to the caller
    db.refresh(user)


# ---------------------------------------------------------------------------
# Module-level singleton (initialized in run_ui.py)
# ---------------------------------------------------------------------------

_auth_manager: AuthManager | None = None


def init_auth(app: Flask) -> AuthManager:
    """Initialize the global AuthManager instance."""
    global _auth_manager  # noqa: PLW0603
    _auth_manager = AuthManager(app)
    return _auth_manager


def get_auth_manager() -> AuthManager:
    """Return the global AuthManager.

    Raises:
        RuntimeError: If ``init_auth()`` has not been called.
    """
    if _auth_manager is None:
        raise RuntimeError("AuthManager not initialized. Call init_auth(app) first.")
    return _auth_manager
