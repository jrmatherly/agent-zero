from python.helpers import runtime
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.file_browser import FileBrowser
from python.helpers.workspace import (
    get_baseline_root,
    get_team_shared_root,
    get_workspace_root,
    resolve_virtual_path,
)


class GetWorkDirFiles(ApiHandler):
    @classmethod
    def get_methods(cls):
        return ["GET"]

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("workdir", "read")

    async def process(self, input: dict, request: Request) -> dict | Response:
        tenant_ctx = self._get_tenant_ctx()
        workspace = get_workspace_root(tenant_ctx)
        baseline_dir = get_baseline_root()
        shared_dir = get_team_shared_root(tenant_ctx)

        current_path = request.args.get("path", "")
        if current_path == "$WORK_DIR":
            current_path = ""

        # At workspace root, return merged view with baseline and shared entries
        if not current_path:
            result = await runtime.call_development_function(
                get_files_merged, current_path, workspace, baseline_dir, shared_dir
            )
            return {"data": result}

        # Route virtual path prefixes to the correct directory
        resolved_dir, sub_path, _readonly = resolve_virtual_path(
            current_path, workspace, baseline_dir, shared_dir
        )

        result = await runtime.call_development_function(
            get_files, sub_path, resolved_dir
        )

        return {"data": result}


async def get_files_merged(path, base_dir, baseline_dir, shared_dir):
    browser = FileBrowser(base_dir=base_dir)
    return browser.get_files_merged(
        path, baseline_dir=baseline_dir, shared_dir=shared_dir
    )


async def get_files(path, base_dir):
    browser = FileBrowser(base_dir=base_dir)
    return browser.get_files(path)
