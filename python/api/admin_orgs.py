import json
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.error_response import safe_error_response


def _org_to_dict(org) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "settings_json": org.settings_json,
        "is_active": org.is_active,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


class AdminOrgs(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("admin", "orgs")

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action")

        if action == "list":
            try:
                with auth_db.get_session() as db:
                    orgs = user_store.list_organizations(db)
                    return {"ok": True, "data": [_org_to_dict(o) for o in orgs]}
            except Exception as e:
                return safe_error_response(e, context="admin_orgs.list")

        elif action == "create":
            name = input.get("name")
            slug = input.get("slug")
            if not name or not slug:
                return Response(
                    json.dumps({"error": "name and slug are required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    org = user_store.create_organization(db, name, slug)
                    db.flush()
                    result = _org_to_dict(org)
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_orgs.create")

        elif action == "update":
            org_id = input.get("org_id")
            if not org_id:
                return Response(
                    json.dumps({"error": "org_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            kwargs = {}
            for key in ("name", "slug", "settings_json"):
                if key in input:
                    kwargs[key] = input[key]
            try:
                with auth_db.get_session() as db:
                    org = user_store.update_organization(db, org_id, **kwargs)
                    result = _org_to_dict(org)
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_orgs.update")

        elif action == "deactivate":
            org_id = input.get("org_id")
            if not org_id:
                return Response(
                    json.dumps({"error": "org_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    user_store.deactivate_organization(db, org_id)
                return {"ok": True}
            except Exception as e:
                return safe_error_response(e, context="admin_orgs.deactivate")

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
