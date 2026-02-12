import os

from python.helpers import branding, git

# Default: check our fork. Override via BRAND_UPDATE_CHECK_URL env var.
# Set to empty string to disable update checks entirely.
_DEFAULT_UPDATE_URL = (
    "https://api.github.com/repos/jrmatherly/apollos-ai/releases/latest"
)


async def check_version():
    import httpx

    url = os.environ.get("BRAND_UPDATE_CHECK_URL", _DEFAULT_UPDATE_URL)
    if not url:
        return {}  # Disabled via env var

    try:
        current_version = git.get_version()

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url, headers={"Accept": "application/vnd.github+json"}
            )
            response.raise_for_status()
            data = response.json()

        tag = data.get("tag_name", "")
        return {
            "latest_version": {
                "tag": tag,
                "name": data.get("name", tag),
                "time": data.get("published_at", ""),
            },
            "notification": _build_notification(current_version, tag, data)
            if tag
            else None,
        }
    except Exception:
        return {}  # Network/HTTP/parse errors — consistent with disabled state


def _is_newer(current: str, latest: str) -> bool:
    """Semantic version comparison. Returns False on parse failure (safe default)."""
    if not current or current == "unknown" or not latest:
        return False
    cur = current.lstrip("v")
    lat = latest.lstrip("v")
    try:
        # packaging is available as transitive dep; add explicitly if needed
        from packaging.version import Version

        return Version(lat) > Version(cur)
    except Exception:
        # Return False on parse failure, not cur != lat
        # A fallback of "different = newer" would false-positive on downgrades
        return False


def _build_notification(current_version, tag, release_data):
    """Build notification only if the latest release is strictly newer."""
    if not _is_newer(current_version, tag):
        return None
    return {
        "id": f"update-{tag}",
        "title": "Newer version available",
        "message": f"A newer version of {branding.BRAND_NAME} is available: {release_data.get('name', tag)}",
        "type": "info",
        "detail": release_data.get("html_url", ""),
        "display_time": 10,
        "group": "update_check",
    }
