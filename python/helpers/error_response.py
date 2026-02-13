import json
import logging
import traceback

from flask import Response

logger = logging.getLogger(__name__)


def safe_error_response(
    e: Exception,
    status: int = 500,
    context: str = "",
    *,
    safe_message: str = "An internal error occurred.",
) -> Response:
    """Return a generic error to the client; log the real error server-side.

    Only the safe_message is returned to the user. The actual exception
    details (message + stack trace) are logged server-side for debugging.
    """
    logger.error(
        "API error%s: %s\n%s",
        f" [{context}]" if context else "",
        str(e),
        traceback.format_exc(),
    )

    return Response(
        json.dumps({"error": safe_message}),
        status=status,
        mimetype="application/json",
    )
