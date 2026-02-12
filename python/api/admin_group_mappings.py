import json
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.error_response import safe_error_response


def _mapping_to_dict(mapping) -> dict:
    return {
        "entra_group_id": mapping.entra_group_id,
        "org_id": mapping.org_id,
        "team_id": mapping.team_id,
        "role": mapping.role,
    }


class AdminGroupMappings(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("admin", "groups")

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
                    mappings = user_store.list_group_mappings(db, org_id)
                    return {
                        "ok": True,
                        "data": [_mapping_to_dict(m) for m in mappings],
                    }
            except Exception as e:
                return safe_error_response(e, context="admin_group_mappings.list")

        elif action == "upsert":
            entra_group_id = input.get("entra_group_id")
            org_id = input.get("org_id")
            if not entra_group_id or not org_id:
                return Response(
                    json.dumps({"error": "entra_group_id and org_id are required"}),
                    status=400,
                    mimetype="application/json",
                )
            team_id = input.get("team_id")
            role = input.get("role", "member")
            try:
                with auth_db.get_session() as db:
                    mapping = user_store.upsert_group_mapping(
                        db, entra_group_id, org_id, team_id=team_id, role=role
                    )
                    result = _mapping_to_dict(mapping)
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_group_mappings.upsert")

        elif action == "delete":
            entra_group_id = input.get("entra_group_id")
            if not entra_group_id:
                return Response(
                    json.dumps({"error": "entra_group_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    user_store.delete_group_mapping(db, entra_group_id)
                return {"ok": True}
            except Exception as e:
                return safe_error_response(e, context="admin_group_mappings.delete")

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
