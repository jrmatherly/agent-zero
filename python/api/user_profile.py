from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response, g
from python.helpers.error_response import safe_error_response


class UserProfile(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return None  # auth-only, no RBAC

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        try:
            user = g.current_user if hasattr(g, "current_user") else None
        except RuntimeError:
            user = None

        if not user:
            return {"user": None, "memberships": []}

        try:
            with auth_db.get_session() as db:
                db_user = user_store.get_user_by_id(db, str(user["id"]))
                if not db_user:
                    return {"user": None, "memberships": []}

                user_info = {
                    "id": db_user.id,
                    "email": db_user.email,
                    "display_name": db_user.display_name,
                    "avatar_url": db_user.avatar_url,
                    "is_system_admin": db_user.is_system_admin,
                    "auth_provider": db_user.auth_provider,
                }

                memberships = []
                for om in db_user.org_memberships:
                    org = om.organization
                    org_entry = {
                        "org_id": org.id,
                        "org_name": org.name,
                        "org_slug": org.slug,
                        "role": om.role,
                        "teams": [],
                    }
                    # Find team memberships within this org
                    for tm in db_user.team_memberships:
                        if tm.team and tm.team.org_id == org.id:
                            org_entry["teams"].append(
                                {
                                    "team_id": tm.team.id,
                                    "team_name": tm.team.name,
                                    "team_slug": tm.team.slug,
                                    "role": tm.role,
                                }
                            )
                    memberships.append(org_entry)

                return {"user": user_info, "memberships": memberships}
        except Exception as e:
            return safe_error_response(e, context="user_profile")
