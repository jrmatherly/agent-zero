import json
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response, g, session
from python.helpers.error_response import safe_error_response


class SwitchContext(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return None  # auth-only, no RBAC

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        org_id = input.get("org_id")
        team_id = input.get("team_id")

        try:
            user = g.current_user if hasattr(g, "current_user") else None
        except RuntimeError:
            user = None

        if not user:
            return Response(
                json.dumps({"error": "Not authenticated"}),
                status=401,
                mimetype="application/json",
            )

        user_id = str(user["id"])

        try:
            with auth_db.get_session() as db:
                # Validate org membership
                if org_id:
                    om = (
                        db.query(user_store.OrgMembership)
                        .filter_by(user_id=user_id, org_id=org_id)
                        .first()
                    )
                    if not om:
                        return Response(
                            json.dumps({"error": "Not a member of this org/team"}),
                            status=403,
                            mimetype="application/json",
                        )

                # Validate team membership
                if team_id:
                    tm = (
                        db.query(user_store.TeamMembership)
                        .filter_by(user_id=user_id, team_id=team_id)
                        .first()
                    )
                    if not tm:
                        return Response(
                            json.dumps({"error": "Not a member of this org/team"}),
                            status=403,
                            mimetype="application/json",
                        )
        except Exception as e:
            return safe_error_response(e, context="switch_context")

        # Update session context
        session["user"]["org_id"] = org_id
        session["user"]["team_id"] = team_id

        return {"ok": True, "org_id": org_id, "team_id": team_id}
