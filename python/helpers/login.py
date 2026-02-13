import hashlib
import hmac
import os

from python.helpers import dotenv


def get_credentials_hash():
    user = dotenv.get_dotenv_value(dotenv.KEY_AUTH_LOGIN)
    password = dotenv.get_dotenv_value(dotenv.KEY_AUTH_PASSWORD)
    if not user:
        return None
    # HMAC-SHA256 for session token derivation (not password storage).
    # Using runtime persistent ID as HMAC key binds the token to this server instance.
    from python.helpers import runtime

    secret = runtime.get_persistent_id().encode()
    return hmac.new(secret, f"{user}:{password}".encode(), hashlib.sha256).hexdigest()


def is_login_required():
    """Check if any authentication mechanism is configured.

    Returns True when legacy single-user auth (AUTH_LOGIN) OR multi-user
    auth (ADMIN_EMAIL with ADMIN_PASSWORD, or OIDC) is configured.
    """
    # Legacy single-user auth
    if dotenv.get_dotenv_value(dotenv.KEY_AUTH_LOGIN):
        return True
    # Multi-user auth: admin account configured
    if os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD"):
        return True
    # Multi-user auth: OIDC SSO configured
    if os.environ.get("OIDC_CLIENT_ID") and os.environ.get("OIDC_TENANT_ID"):
        return True
    return False
