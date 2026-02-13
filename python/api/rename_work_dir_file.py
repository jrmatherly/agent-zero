from python.api import get_work_dir_files
from python.helpers import runtime
from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers.file_browser import FileBrowser
from python.helpers.workspace import (
    get_baseline_root,
    get_team_shared_root,
    get_workspace_root,
    resolve_virtual_path,
)


class RenameWorkDirFile(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("workdir", "write")

    async def process(self, input: Input, request: Request) -> Output:
        try:
            tenant_ctx = self._get_tenant_ctx()
            workspace = get_workspace_root(tenant_ctx)
            baseline_dir = get_baseline_root()
            shared_dir = get_team_shared_root(tenant_ctx)

            action = input.get("action", "rename")
            new_name = (input.get("newName", "") or "").strip()
            if not new_name:
                return {"error": "New name is required"}

            current_path = input.get("currentPath", "")

            if action == "create-folder":
                parent_path = input.get("parentPath", current_path)
                if not parent_path:
                    return {"error": "Parent path is required"}

                if parent_path.startswith("$BASELINE"):
                    return {"error": "Baseline files are read-only"}

                resolved_dir, resolved_parent, _readonly = resolve_virtual_path(
                    parent_path, workspace, baseline_dir, shared_dir
                )
                res = await runtime.call_development_function(
                    create_folder, resolved_parent, new_name, resolved_dir
                )
            else:
                file_path = input.get("path", "")
                if not file_path:
                    return {"error": "Path is required"}

                if file_path.startswith("$BASELINE") or current_path.startswith(
                    "$BASELINE"
                ):
                    return {"error": "Baseline files are read-only"}

                resolved_dir, resolved_path, _readonly = resolve_virtual_path(
                    file_path, workspace, baseline_dir, shared_dir
                )
                if not resolved_path.startswith("/"):
                    resolved_path = f"/{resolved_path}"
                res = await runtime.call_development_function(
                    rename_item, resolved_path, new_name, resolved_dir
                )

            if res:
                result = await runtime.call_development_function(
                    get_work_dir_files.get_files, current_path, workspace
                )
                return {"data": result}

            error_msg = (
                "Failed to create folder"
                if action == "create-folder"
                else "Rename failed"
            )
            return {"error": error_msg}

        except Exception as e:
            return {"error": str(e)}


async def rename_item(file_path: str, new_name: str, base_dir: str) -> bool:
    browser = FileBrowser(base_dir=base_dir)
    return browser.rename_item(file_path, new_name)


async def create_folder(parent_path: str, folder_name: str, base_dir: str) -> bool:
    browser = FileBrowser(base_dir=base_dir)
    return browser.create_folder(parent_path, folder_name)
