import json
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.error_response import safe_error_response


def _user_to_dict(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "auth_provider": user.auth_provider,
        "primary_org_id": user.primary_org_id,
        "is_active": user.is_active,
        "is_system_admin": user.is_system_admin,
        "settings_json": user.settings_json,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


class AdminUsers(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("admin", "users")

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action")

        if action == "list":
            org_id = input.get("org_id")
            team_id = input.get("team_id")
            try:
                with auth_db.get_session() as db:
                    users = user_store.list_users(db, org_id=org_id, team_id=team_id)
                    return {"ok": True, "data": [_user_to_dict(u) for u in users]}
            except Exception as e:
                return safe_error_response(e, context="admin_users.list")

        elif action == "invite":
            email = input.get("email")
            password = input.get("password")
            if not email or not password:
                return Response(
                    json.dumps({"error": "email and password are required"}),
                    status=400,
                    mimetype="application/json",
                )
            display_name = input.get("display_name")
            org_id = input.get("org_id")
            team_id = input.get("team_id")
            role = input.get("role", "member")
            try:
                with auth_db.get_session() as db:
                    user = user_store.create_local_user(
                        db, email, password, display_name
                    )
                    db.flush()
                    if org_id:
                        user_store.set_user_role(db, user.id, org_id=org_id, role=role)
                    if team_id:
                        user_store.set_user_role(
                            db, user.id, team_id=team_id, role=role
                        )
                    result = _user_to_dict(user)
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_users.invite")

        elif action == "update_role":
            user_id = input.get("user_id")
            if not user_id:
                return Response(
                    json.dumps({"error": "user_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            org_id = input.get("org_id")
            team_id = input.get("team_id")
            role = input.get("role", "member")
            try:
                with auth_db.get_session() as db:
                    user_store.set_user_role(
                        db, user_id, org_id=org_id, team_id=team_id, role=role
                    )
                return {"ok": True}
            except Exception as e:
                return safe_error_response(e, context="admin_users.update_role")

        elif action == "deactivate":
            user_id = input.get("user_id")
            if not user_id:
                return Response(
                    json.dumps({"error": "user_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    user_store.deactivate_user(db, user_id)
                return {"ok": True}
            except Exception as e:
                return safe_error_response(e, context="admin_users.deactivate")

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
