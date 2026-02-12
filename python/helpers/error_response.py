import json
import logging
import traceback

from flask import Response

from python.helpers import runtime

logger = logging.getLogger(__name__)


def safe_error_response(
    e: Exception,
    status: int = 500,
    context: str = "",
    *,
    safe_message: str = "An internal error occurred.",
) -> Response:
    """Return a generic error to the client; log the real error server-side.

    In development mode (non-Docker), the actual exception message is included
    for easier debugging. In production, only the safe_message is returned.
    """
    logger.error(
        "API error%s: %s\n%s",
        f" [{context}]" if context else "",
        str(e),
        traceback.format_exc(),
    )

    if runtime.is_development():
        msg = str(e)
    else:
        msg = safe_message

    return Response(
        json.dumps({"error": msg}),
        status=status,
        mimetype="application/json",
    )
