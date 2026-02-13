import base64

from werkzeug.datastructures import FileStorage

from python.api import get_work_dir_files
from python.helpers import runtime
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.file_browser import FileBrowser
from python.helpers.workspace import (
    get_baseline_root,
    get_team_shared_root,
    get_workspace_root,
    resolve_virtual_path,
)


class UploadWorkDirFiles(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("workdir", "write")

    async def process(self, input: dict, request: Request) -> dict | Response:
        tenant_ctx = self._get_tenant_ctx()
        workspace = get_workspace_root(tenant_ctx)
        baseline_dir = get_baseline_root()
        shared_dir = get_team_shared_root(tenant_ctx)

        if "files[]" not in request.files:
            raise Exception("No files uploaded")

        current_path = request.form.get("path", "")

        if current_path.startswith("$BASELINE"):
            return {"error": "Baseline files are read-only"}

        resolved_dir, resolved_path, _readonly = resolve_virtual_path(
            current_path, workspace, baseline_dir, shared_dir
        )

        uploaded_files = request.files.getlist("files[]")

        successful, failed = await upload_files(
            uploaded_files, resolved_path, resolved_dir
        )

        if not successful and failed:
            raise Exception("All uploads failed")

        result = await runtime.call_development_function(
            get_work_dir_files.get_files, current_path, workspace
        )

        return {
            "message": (
                "Files uploaded successfully"
                if not failed
                else "Some files failed to upload"
            ),
            "data": result,
            "successful": successful,
            "failed": failed,
        }


async def upload_files(
    uploaded_files: list[FileStorage], current_path: str, base_dir: str
):
    if runtime.is_development():
        successful = []
        failed = []
        for file in uploaded_files:
            file_content = file.stream.read()
            base64_content = base64.b64encode(file_content).decode("utf-8")
            if await runtime.call_development_function(
                upload_file, current_path, file.filename, base64_content, base_dir
            ):
                successful.append(file.filename)
            else:
                failed.append(file.filename)
    else:
        browser = FileBrowser(base_dir=base_dir)
        successful, failed = browser.save_files(uploaded_files, current_path)

    return successful, failed


async def upload_file(
    current_path: str, filename: str, base64_content: str, base_dir: str
):
    browser = FileBrowser(base_dir=base_dir)
    return browser.save_file_b64(current_path, filename, base64_content)
