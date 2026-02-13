from python.helpers import runtime
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.file_browser import FileBrowser
from python.helpers.workspace import get_workspace_root


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

        current_path = request.args.get("path", "")
        if current_path == "$WORK_DIR":
            current_path = ""

        result = await runtime.call_development_function(
            get_files, current_path, workspace
        )

        return {"data": result}


async def get_files(path, base_dir):
    browser = FileBrowser(base_dir=base_dir)
    return browser.get_files(path)
