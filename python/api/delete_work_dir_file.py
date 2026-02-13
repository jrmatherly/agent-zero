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


class DeleteWorkDirFile(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("workdir", "write")

    async def process(self, input: Input, request: Request) -> Output:
        try:
            tenant_ctx = self._get_tenant_ctx()
            workspace = get_workspace_root(tenant_ctx)
            baseline_dir = get_baseline_root()
            shared_dir = get_team_shared_root(tenant_ctx)

            file_path = input.get("path", "")
            current_path = input.get("currentPath", "")

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
                delete_file, resolved_path, resolved_dir
            )

            if res:
                result = await runtime.call_development_function(
                    get_work_dir_files.get_files, current_path, workspace
                )
                return {"data": result}
            else:
                return {"error": "File not found or could not be deleted"}
        except Exception as e:
            return {"error": str(e)}


async def delete_file(file_path: str, base_dir: str):
    browser = FileBrowser(base_dir=base_dir)
    return browser.delete_file(file_path)
