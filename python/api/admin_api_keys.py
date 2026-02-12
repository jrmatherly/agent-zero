import json
from typing import Any

from python.helpers import auth_db, user_store
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.error_response import safe_error_response


class AdminApiKeys(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("admin", "keys")

    async def process(
        self, input: dict[Any, Any], request: Request
    ) -> dict[Any, Any] | Response:
        action = input.get("action")

        if action == "list":
            owner_type = input.get("owner_type")
            owner_id = input.get("owner_id")
            if not owner_type or not owner_id:
                return Response(
                    json.dumps({"error": "owner_type and owner_id are required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    keys = user_store.list_vault_keys(db, owner_type, owner_id)
                    return {"ok": True, "data": keys}
            except Exception as e:
                return safe_error_response(e, context="admin_api_keys.list")

        elif action == "store":
            owner_type = input.get("owner_type")
            owner_id = input.get("owner_id")
            key_name = input.get("key_name")
            value = input.get("value")
            if not owner_type or not owner_id or not key_name or not value:
                return Response(
                    json.dumps(
                        {
                            "error": "owner_type, owner_id, key_name, and value are required"
                        }
                    ),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    entry = user_store.store_vault_key(
                        db, owner_type, owner_id, key_name, value
                    )
                    db.flush()
                    result = {
                        "id": entry.id,
                        "owner_type": entry.owner_type,
                        "owner_id": entry.owner_id,
                        "key_name": entry.key_name,
                        "created_at": (
                            entry.created_at.isoformat() if entry.created_at else None
                        ),
                    }
                return {"ok": True, "data": result}
            except Exception as e:
                return safe_error_response(e, context="admin_api_keys.store")

        elif action == "delete":
            vault_id = input.get("vault_id")
            if not vault_id:
                return Response(
                    json.dumps({"error": "vault_id is required"}),
                    status=400,
                    mimetype="application/json",
                )
            try:
                with auth_db.get_session() as db:
                    user_store.delete_vault_key(db, vault_id)
                return {"ok": True}
            except Exception as e:
                return safe_error_response(e, context="admin_api_keys.delete")

        return Response(
            json.dumps({"error": f"Unknown action: {action}"}),
            status=400,
            mimetype="application/json",
        )
