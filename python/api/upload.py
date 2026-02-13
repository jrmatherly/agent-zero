from python.helpers import files
from python.helpers.api import ApiHandler, Request, Response
from python.helpers.security import safe_filename


class UploadFile(ApiHandler):
    @classmethod
    def get_required_permission(cls) -> tuple[str, str] | None:
        return ("chats", "write")

    async def process(self, input: dict, request: Request) -> dict | Response:
        if "file" not in request.files:
            raise Exception("No file part")

        file_list = request.files.getlist("file")  # Handle multiple files
        saved_filenames = []

        for file in file_list:
            if file and self.allowed_file(file.filename):  # Check file type
                if not file.filename:
                    continue
                filename = safe_filename(file.filename)
                if not filename:
                    continue
                tenant_ctx = self._get_tenant_ctx()
                if not tenant_ctx.is_system:
                    uploads_dir = tenant_ctx.uploads_dir
                else:
                    uploads_dir = "usr/uploads"
                file.save(files.get_abs_path(uploads_dir, filename))
                saved_filenames.append(filename)

        return {"filenames": saved_filenames}  # Return saved filenames

    ALLOWED_EXTENSIONS = {
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".ico",
        ".tiff",
        # Documents
        ".txt",
        ".pdf",
        ".csv",
        ".md",
        ".rst",
        ".rtf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        # Code / config
        ".html",
        ".css",
        ".js",
        ".ts",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".sh",
        ".bash",
        ".py",
        ".rb",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        # Archives
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        # Data
        ".sql",
        ".db",
        ".sqlite",
        ".parquet",
        ".ndjson",
        ".jsonl",
        # Other
        ".log",
        ".wav",
        ".mp3",
        ".mp4",
        ".webm",
        ".ogg",
    }

    def allowed_file(self, filename):
        if not filename:
            return False
        from pathlib import Path

        ext = Path(filename).suffix.lower()
        return ext in self.ALLOWED_EXTENSIONS
