import mimetypes
import os

from python.helpers import files, runtime
from python.helpers.api import ApiHandler, Input, Output, Request
from python.helpers.file_browser import FileBrowser
from python.helpers.workspace import (
    get_baseline_root,
    get_team_shared_root,
    get_workspace_root,
    resolve_virtual_path,
)

MAX_EDIT_FILE_SIZE = 1024 * 1024
BINARY_SAMPLE_SIZE = 10 * 1024


class EditWorkDirFile(ApiHandler):
    @classmethod
    def get_methods(cls):
        return ["GET", "POST"]

    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("workdir", "write")

    def _extract_error_message(self, error_str: str) -> str:
        """Extract user-friendly error message from exception string."""
        for line in reversed(error_str.split("\n")):
            if ": " in line and ("Exception" in line or "Error" in line):
                return line.split(": ", 1)[1].strip()
        return error_str.strip()

    async def process(self, input: Input, request: Request) -> Output:
        try:
            tenant_ctx = self._get_tenant_ctx()
            workspace = get_workspace_root(tenant_ctx)
            baseline_dir = get_baseline_root()
            shared_dir = get_team_shared_root(tenant_ctx)

            if request.method == "GET":
                file_path = request.args.get("path", "")
                if not file_path:
                    return {"error": "Path is required"}

                resolved_dir, resolved_path, _readonly = resolve_virtual_path(
                    file_path, workspace, baseline_dir, shared_dir
                )
                if not resolved_path.startswith("/"):
                    resolved_path = f"/{resolved_path}"

                data = await runtime.call_development_function(
                    load_file, resolved_path, resolved_dir
                )
                return {"data": data}

            file_path = input.get("path", "")
            if not file_path:
                return {"error": "Path is required"}

            if file_path.startswith("$BASELINE"):
                return {"error": "Baseline files are read-only"}

            resolved_dir, resolved_path, _readonly = resolve_virtual_path(
                file_path, workspace, baseline_dir, shared_dir
            )
            if not resolved_path.startswith("/"):
                resolved_path = f"/{resolved_path}"

            content = input.get("content", "")
            if not isinstance(content, str):
                return {"error": "Content must be a string"}

            content_size = len(content.encode("utf-8"))
            if content_size > MAX_EDIT_FILE_SIZE:
                return {"error": "File exceeds 1 MB and cannot be edited"}

            res = await runtime.call_development_function(
                save_file, resolved_path, content, resolved_dir
            )
            if not res:
                return {"error": "Failed to save file"}

            return {"ok": True}
        except Exception as e:
            # Extract clean error message from exception
            # RPC calls may return full tracebacks in exception strings
            return {"error": self._extract_error_message(str(e))}


async def load_file(file_path: str, base_dir: str) -> dict:
    browser = FileBrowser(base_dir=base_dir)
    full_path = browser.get_full_path(file_path)

    if os.path.isdir(full_path):
        raise Exception("Path points to a directory")

    size = os.path.getsize(full_path)
    if size > MAX_EDIT_FILE_SIZE:
        raise Exception("File exceeds 1 MB and cannot be edited")

    # Binary detection: only sample the first ~10KB (per backend rules)
    if files.is_probably_binary_file(full_path, sample_size=BINARY_SAMPLE_SIZE):
        raise Exception("Binary file detected; editing is not supported")

    mime_type, _ = mimetypes.guess_type(full_path)
    try:
        with open(full_path, "r", encoding="utf-8", errors="strict") as file:
            content = file.read()
    except UnicodeDecodeError:
        raise Exception("Unable to decode file as UTF-8; editing is not supported")

    return {
        "path": file_path,
        "name": os.path.basename(full_path),
        "mime_type": mime_type or "text/plain",
        "content": content,
    }


def save_file(file_path: str, content: str, base_dir: str) -> bool:
    browser = FileBrowser(base_dir=base_dir)
    return browser.save_text_file(file_path, content)
