import json
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.error_response import safe_error_response


def _team_to_dict(team) -> dict:
    return {
        "id": team.id,
        "org_id": team.org_id,
        "name": team.name,
        "slug": team.slug,
        "settings_json": team.settings_json,
        "created_at": team.created_at.isoformat() if team.created_at else None,
    }


class AdminTeams(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("admin", "teams")

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action")

        if action == "list":
            org_id = input.get("org_id")
            if not org_id:
                return Response(
                    json.dumps({"error": "org_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    teams = user_store.list_teams(db, org_id)
                    return {"ok": True, "data": [_team_to_dict(t) for t in teams]}
            except Exception as e:
                return safe_error_response(e, context="admin_teams.list")

        elif action == "create":
            org_id = input.get("org_id")
            name = input.get("name")
            slug = input.get("slug")
            if not org_id or not name or not slug:
                return Response(
                    json.dumps({"error": "org_id, name, and slug are required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    team = user_store.create_team(db, org_id, name, slug)
                    db.flush()
                    result = _team_to_dict(team)
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_teams.create")

        elif action == "update":
            team_id = input.get("team_id")
            if not team_id:
                return Response(
                    json.dumps({"error": "team_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            kwargs = {}
            for key in ("name", "slug", "settings_json"):
                if key in input:
                    kwargs[key] = input[key]
            try:
                with auth_db.get_session() as db:
                    team = user_store.update_team(db, team_id, **kwargs)
                    result = _team_to_dict(team)
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_teams.update")

        elif action == "delete":
            team_id = input.get("team_id")
            if not team_id:
                return Response(
                    json.dumps({"error": "team_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    user_store.delete_team(db, team_id)
                return {"ok": True}
            except Exception as e:
                return safe_error_response(e, context="admin_teams.delete")

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
