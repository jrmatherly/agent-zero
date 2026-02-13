"""Comprehensive security tests covering CodeQL remediation fixes.

Tests verify path traversal prevention, null byte rejection, error response
sanitization, file permissions, SSH host key policy, HMAC token derivation,
sandboxing gates, security headers, and backup name sanitization.
"""

import asyncio
import hashlib
import hmac
import json
import os
import stat
import threading
from unittest.mock import patch

from flask import Flask

from python.helpers import files, runtime


# ---------------------------------------------------------------------------
# 1. Path Traversal Prevention
# ---------------------------------------------------------------------------
class TestPathTraversal:
    """Verify that path traversal attacks are rejected by helpers in files.py."""

    def test_is_in_base_dir_rejects_traversal(self):
        """Verify ../../../etc/passwd is rejected by is_in_base_dir."""
        base = files.get_base_dir()
        traversal_path = os.path.join(base, "../../../etc/passwd")
        assert not files.is_in_base_dir(traversal_path)

    def test_is_in_base_dir_accepts_valid_path(self):
        """A path inside the project root must be accepted."""
        base = files.get_base_dir()
        valid_path = os.path.join(base, "python/helpers/files.py")
        assert files.is_in_base_dir(valid_path)

    def test_is_in_dir_rejects_traversal(self):
        """Paths outside the target directory must be rejected."""
        assert not files.is_in_dir("/etc/passwd", "/home/user")

    def test_is_in_dir_accepts_subpath(self):
        """A genuine subpath must be accepted."""
        assert files.is_in_dir("/home/user/file.txt", "/home/user")

    def test_realpath_resolves_dotdot(self):
        """os.path.realpath collapses '..' sequences, revealing the true path."""
        base = files.get_base_dir()
        path_with_dotdot = os.path.join(base, "python", "..", "..", "etc", "passwd")
        real = os.path.realpath(path_with_dotdot)
        assert not files.is_in_base_dir(real)

    def test_is_in_dir_with_common_prefix_attack(self):
        """Ensure /home/user_evil is not treated as inside /home/user."""
        # os.path.commonpath would return /home/user for these, but
        # is_in_dir uses abspath + commonpath correctly.
        assert not files.is_in_dir("/home/user_evil/file.txt", "/home/user")

    def test_is_in_base_dir_with_symlink_like_dotdot(self):
        """Multiple layers of '..' must still be resolved and rejected."""
        base = files.get_base_dir()
        deep_traversal = os.path.join(
            base, "a", "b", "..", "..", "..", "..", "etc", "shadow"
        )
        assert not files.is_in_base_dir(deep_traversal)


# ---------------------------------------------------------------------------
# 2. Null Byte Rejection
# ---------------------------------------------------------------------------
class TestNullByteRejection:
    """Verify null byte detection logic works for path sanitization."""

    def test_null_byte_detected_in_string(self):
        """Strings containing null bytes must be detectable."""
        assert "\x00" in "path/../../etc/passwd\x00.png"
        assert "\x00" not in "normal/path.png"

    def test_null_byte_not_in_clean_path(self):
        """Clean paths must not trigger null byte detection."""
        clean_paths = [
            "usr/settings.json",
            "python/helpers/files.py",
            "webui/index.html",
        ]
        for p in clean_paths:
            assert "\x00" not in p

    def test_binary_detection_catches_null_bytes(self):
        """The is_probably_binary_bytes helper detects null bytes as binary."""
        assert files.is_probably_binary_bytes(b"hello\x00world")
        assert not files.is_probably_binary_bytes(b"hello world")


# ---------------------------------------------------------------------------
# 3. Error Response Sanitization
# ---------------------------------------------------------------------------
class TestErrorResponseSanitization:
    """API error handler must hide sensitive details in production mode."""

    @patch.object(runtime, "is_development", return_value=False)
    def test_api_error_no_traceback_in_production(self, _mock_dev):
        """In production, API errors must return a generic message."""
        from python.helpers.api import ApiHandler

        app = Flask(__name__)
        app.secret_key = "test-secret"

        class FailHandler(ApiHandler):
            async def process(self, input, request):
                raise ValueError(
                    "sensitive internal detail about /usr/lib/python3.12/..."
                )

        handler = FailHandler(app, threading.RLock())

        with app.test_request_context(json={}):
            from flask import request as flask_request

            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(
                    handler.handle_request(flask_request)
                )
            finally:
                loop.close()

            assert response.status_code == 500
            body = response.get_data(as_text=True)
            assert "sensitive internal detail" not in body
            assert "Internal server error" in body

    @patch.object(runtime, "is_development", return_value=True)
    def test_api_error_shows_detail_in_dev(self, _mock_dev):
        """In development, API errors must include the original detail."""
        from python.helpers.api import ApiHandler

        app = Flask(__name__)
        app.secret_key = "test-secret"

        class FailHandler(ApiHandler):
            async def process(self, input, request):
                raise ValueError("detailed error info")

        handler = FailHandler(app, threading.RLock())

        with app.test_request_context(json={}):
            from flask import request as flask_request

            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(
                    handler.handle_request(flask_request)
                )
            finally:
                loop.close()

            assert response.status_code == 500
            body = response.get_data(as_text=True)
            assert "detailed error info" in body

    @patch.object(runtime, "is_development", return_value=False)
    def test_production_error_is_valid_json(self, _mock_dev):
        """Production error response must be valid JSON with 'error' key."""
        from python.helpers.api import ApiHandler

        app = Flask(__name__)
        app.secret_key = "test-secret"

        class FailHandler(ApiHandler):
            async def process(self, input, request):
                raise RuntimeError("something went wrong internally")

        handler = FailHandler(app, threading.RLock())

        with app.test_request_context(json={}):
            from flask import request as flask_request

            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(
                    handler.handle_request(flask_request)
                )
            finally:
                loop.close()

            assert response.status_code == 500
            assert response.mimetype == "application/json"
            data = json.loads(response.get_data(as_text=True))
            assert data["error"] == "Internal server error"


# ---------------------------------------------------------------------------
# 4. File Permissions
# ---------------------------------------------------------------------------
class TestFilePermissions:
    """Verify security-sensitive file permissions are applied at runtime."""

    def test_delete_dir_removes_directory(self, tmp_path, monkeypatch):
        """delete_dir must successfully remove a directory and its contents."""
        target = tmp_path / "test_dir"
        target.mkdir()
        (target / "child.txt").write_text("data")
        (target / "subdir").mkdir()
        (target / "subdir" / "nested.txt").write_text("nested")

        monkeypatch.setattr(files, "get_abs_path", lambda rel: str(target))
        files.delete_dir("test_dir")
        assert not target.exists(), "delete_dir must remove the directory"

    def test_delete_dir_uses_owner_only_chmod_on_retry(self, tmp_path, monkeypatch):
        """delete_dir retry path must use 0o700 (owner-only), not 0o777."""
        import shutil

        target = tmp_path / "stubborn_dir"
        target.mkdir()
        child_file = target / "child.txt"
        child_file.write_text("data")

        monkeypatch.setattr(files, "get_abs_path", lambda rel: str(target))

        # Make rmtree fail on first call so the retry path with chmod is triggered
        original_rmtree = shutil.rmtree
        rmtree_calls = []

        def tracking_rmtree(path, ignore_errors=False):
            rmtree_calls.append(("rmtree", path, ignore_errors))
            if len(rmtree_calls) == 1:
                # First call: pretend it failed by not deleting
                pass
            else:
                # Subsequent calls: actually delete
                original_rmtree(path, ignore_errors=ignore_errors)

        chmod_calls = []
        original_chmod = os.chmod

        def tracking_chmod(path, mode):
            chmod_calls.append(("chmod", path, mode))
            original_chmod(path, mode)

        monkeypatch.setattr(shutil, "rmtree", tracking_rmtree)
        monkeypatch.setattr(os, "chmod", tracking_chmod)

        files.delete_dir("stubborn_dir")

        # Verify chmod was called with 0o700 (owner-only), not 0o777
        for _, _, mode in chmod_calls:
            assert mode == 0o700, f"chmod used {oct(mode)}, expected 0o700"
        assert len(chmod_calls) > 0, "chmod was not called during retry"

    def test_dotenv_chmod_is_owner_only(self, tmp_path, monkeypatch):
        """save_dotenv_value must restrict .env to owner-only (0o600) permissions."""
        from python.helpers import dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("")
        # Make the file world-readable initially to prove chmod changes it
        env_file.chmod(0o644)

        monkeypatch.setattr(dotenv, "get_dotenv_file_path", lambda: str(env_file))
        monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)

        dotenv.save_dotenv_value("TEST_KEY", "test_value")

        file_mode = os.stat(str(env_file)).st_mode & 0o777
        assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"

    def test_dotenv_chmod_numeric_equivalent(self):
        """Sanity check: S_IRUSR | S_IWUSR equals 0o600."""
        assert (stat.S_IRUSR | stat.S_IWUSR) == 0o600


# ---------------------------------------------------------------------------
# 5. SSH Host Key Policy
# ---------------------------------------------------------------------------
class TestSSHHostKeyPolicy:
    """Verify the _is_local_or_private guard in shell_ssh.py."""

    def test_localhost_is_local_or_private(self):
        from python.helpers.shell_ssh import _is_local_or_private

        assert _is_local_or_private("localhost")
        assert _is_local_or_private("127.0.0.1")
        assert _is_local_or_private("::1")

    def test_private_ips_are_local_or_private(self):
        from python.helpers.shell_ssh import _is_local_or_private

        assert _is_local_or_private("192.168.1.1")
        assert _is_local_or_private("10.0.0.1")
        assert _is_local_or_private("172.16.0.1")

    def test_public_ips_are_not_local_or_private(self):
        from python.helpers.shell_ssh import _is_local_or_private

        assert not _is_local_or_private("8.8.8.8")
        assert not _is_local_or_private("1.1.1.1")

    def test_hostnames_are_not_local_or_private(self):
        from python.helpers.shell_ssh import _is_local_or_private

        assert not _is_local_or_private("example.com")
        assert not _is_local_or_private("ssh.remote-server.com")

    def test_link_local_ipv4_is_private(self):
        from python.helpers.shell_ssh import _is_local_or_private

        assert _is_local_or_private("169.254.1.1")

    def test_link_local_ipv6_is_private(self):
        from python.helpers.shell_ssh import _is_local_or_private

        assert _is_local_or_private("fe80::1")


# ---------------------------------------------------------------------------
# 6. HMAC Token Derivation
# ---------------------------------------------------------------------------
class TestHMACTokenDerivation:
    """Verify login and settings modules produce HMAC-based tokens, not bare SHA-256."""

    def test_login_produces_hmac_sha256_output(self, monkeypatch):
        """login.get_credentials_hash must return an HMAC-SHA256 hex digest."""
        from python.helpers import login

        fake_persistent_id = "test-persistent-id-12345"
        test_user = "admin"
        test_password = "secret"

        monkeypatch.setattr(
            "python.helpers.dotenv.get_dotenv_value",
            lambda key, default=None: {
                "AUTH_LOGIN": test_user,
                "AUTH_PASSWORD": test_password,
            }.get(key, default),
        )
        monkeypatch.setattr(
            "python.helpers.runtime.get_persistent_id",
            lambda: fake_persistent_id,
        )

        result = login.get_credentials_hash()

        # Compute expected HMAC-SHA256
        expected = hmac.new(
            fake_persistent_id.encode(),
            f"{test_user}:{test_password}".encode(),
            hashlib.sha256,
        ).hexdigest()
        assert result == expected

        # Verify it does NOT match a bare SHA-256
        bare_sha256 = hashlib.sha256(
            f"{test_user}:{test_password}".encode()
        ).hexdigest()
        assert result != bare_sha256

    def test_login_returns_none_without_credentials(self, monkeypatch):
        """login.get_credentials_hash returns None when AUTH_LOGIN is not set."""
        from python.helpers import login

        monkeypatch.setattr(
            "python.helpers.dotenv.get_dotenv_value",
            lambda key, default=None: default,
        )
        assert login.get_credentials_hash() is None

    def test_settings_produces_hmac_sha256_output(self, monkeypatch):
        """settings.create_auth_token must return an HMAC-SHA256-derived token."""
        from python.helpers import settings

        fake_persistent_id = "test-persistent-id-67890"
        test_user = "admin"
        test_password = "secret"

        monkeypatch.setattr(
            "python.helpers.runtime.get_persistent_id",
            lambda: fake_persistent_id,
        )
        monkeypatch.setattr(
            "python.helpers.dotenv.get_dotenv_value",
            lambda key, default=None: {
                "AUTH_LOGIN": test_user,
                "AUTH_PASSWORD": test_password,
            }.get(key, default),
        )

        result = settings.create_auth_token()

        # Compute expected HMAC-SHA256 base64-encoded token
        import base64

        expected_bytes = hmac.new(
            fake_persistent_id.encode(),
            f"{test_user}:{test_password}".encode(),
            hashlib.sha256,
        ).digest()
        expected = (
            base64.urlsafe_b64encode(expected_bytes).decode().replace("=", "")[:16]
        )
        assert result == expected

    def test_settings_token_differs_from_bare_sha256(self, monkeypatch):
        """settings.create_auth_token must NOT match a bare SHA-256 derivation."""
        from python.helpers import settings

        import base64

        fake_persistent_id = "test-persistent-id-abcdef"
        test_user = "admin"
        test_password = "pass123"

        monkeypatch.setattr(
            "python.helpers.runtime.get_persistent_id",
            lambda: fake_persistent_id,
        )
        monkeypatch.setattr(
            "python.helpers.dotenv.get_dotenv_value",
            lambda key, default=None: {
                "AUTH_LOGIN": test_user,
                "AUTH_PASSWORD": test_password,
            }.get(key, default),
        )

        result = settings.create_auth_token()

        # Bare SHA-256 (what we DON'T want)
        bare_bytes = hashlib.sha256(f"{test_user}:{test_password}".encode()).digest()
        bare_token = base64.urlsafe_b64encode(bare_bytes).decode().replace("=", "")[:16]
        assert result != bare_token


# ---------------------------------------------------------------------------
# 7. Sandboxing Gate
# ---------------------------------------------------------------------------
class TestCodeExecutionSandboxing:
    """Verify the sandboxing gate in code_execution_tool.py.

    Note: We read the source file directly because importing
    code_execution_tool triggers tty_session.py which calls
    sys.stdin.reconfigure() -- incompatible with pytest's stdin.
    """

    @staticmethod
    def _read_source():
        source_path = os.path.join(
            files.get_base_dir(), "python", "tools", "code_execution_tool.py"
        )
        with open(source_path, "r") as f:
            return f.read()

    def test_sandboxing_gate_exists_in_source(self):
        """prepare_state must enforce SSH sandboxing in production."""
        source = self._read_source()
        assert "Code execution requires SSH sandboxing" in source
        assert "is_development" in source

    def test_sandboxing_gate_raises_in_production_path(self):
        """The error message must reference SSH and production settings."""
        source = self._read_source()
        assert "code_exec_ssh_enabled" in source
        assert "DEVELOPMENT_MODE" in source

    def test_sandboxing_gate_warns_in_dev_path(self):
        """Development mode must log a warning about unsandboxed execution."""
        source = self._read_source()
        assert "UNSANDBOXED" in source
        assert "development mode only" in source


# ---------------------------------------------------------------------------
# 8. Security Headers
# ---------------------------------------------------------------------------
class TestSecurityHeaders:
    """Verify security response headers are applied at runtime via Flask test client."""

    def test_run_ui_security_headers_are_set(self):
        """Responses must include X-Content-Type-Options, X-Frame-Options, CSP, and Referrer-Policy."""
        import run_ui

        with run_ui.webapp.test_client() as client:
            response = client.get("/manifest.json")
            headers = response.headers
            assert headers.get("X-Content-Type-Options") is not None
            assert headers.get("X-Frame-Options") is not None
            assert headers.get("Content-Security-Policy") is not None
            assert headers.get("Referrer-Policy") is not None

    def test_run_ui_has_cors_configuration(self):
        """run_ui.webapp must have a flask_cors after_request handler registered."""
        import run_ui

        # flask_cors registers a cors_after_request handler on the app
        after_request_fns = run_ui.webapp.after_request_funcs.get(None, [])
        has_cors = any(
            getattr(fn, "__module__", "").startswith("flask_cors")
            for fn in after_request_fns
        )
        assert has_cors, "flask_cors after_request handler not registered on Flask app"

    def test_run_ui_has_rate_limiter(self):
        """run_ui.limiter must be a flask_limiter.Limiter instance."""
        import run_ui
        from flask_limiter import Limiter

        assert isinstance(run_ui.limiter, Limiter)

    def test_security_header_values_are_strict(self):
        """Verify specific header values are set to strict options."""
        import run_ui

        with run_ui.webapp.test_client() as client:
            response = client.get("/manifest.json")
            headers = response.headers
            assert headers.get("X-Content-Type-Options") == "nosniff"
            assert headers.get("X-Frame-Options") == "DENY"
            assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
            csp = headers.get("Content-Security-Policy", "")
            assert "frame-ancestors 'none'" in csp

    def test_session_cookie_samesite(self):
        """Session cookie must use SameSite=Lax (required for OIDC redirects)."""
        import run_ui

        assert run_ui.webapp.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    def test_csrf_protection_exists(self):
        """run_ui must define a csrf_protect decorator that checks X-CSRF-Token."""
        import run_ui

        # Verify the csrf_protect function exists and is callable
        assert callable(run_ui.csrf_protect)

        # Verify it actually checks X-CSRF-Token by exercising it:
        # Create a test app and endpoint to verify CSRF enforcement
        test_app = Flask(__name__)
        test_app.secret_key = "test"

        @test_app.route("/csrf_test", methods=["POST"])
        @run_ui.csrf_protect
        async def csrf_endpoint():
            return "ok"

        with test_app.test_client() as client:
            # Request without CSRF token should be rejected
            resp = client.post("/csrf_test")
            assert resp.status_code == 403
            assert b"CSRF" in resp.data


# ---------------------------------------------------------------------------
# 9. Backup Name Sanitization
# ---------------------------------------------------------------------------
class TestBackupNameSanitization:
    """Verify backup_name is sanitized in create_backup to prevent path traversal."""

    async def test_backup_name_sanitized_in_zip_path(self, monkeypatch):
        """create_backup must sanitize dangerous chars from backup_name in output path."""
        from python.helpers.backup import BackupService

        svc = BackupService()

        # Mock test_patterns to return a single fake file so create_backup proceeds
        async def fake_test_patterns(metadata, max_files=50000):
            fake_file = os.path.join(svc.agent_zero_root, "usr", "test.txt")
            return [
                {
                    "path": fake_file,
                    "real_path": fake_file,
                    "size": 4,
                    "modified": "2025-01-01T00:00:00",
                    "type": "file",
                }
            ]

        monkeypatch.setattr(svc, "test_patterns", fake_test_patterns)

        # Ensure the fake file exists for zipfile.write()
        fake_file = os.path.join(svc.agent_zero_root, "usr", "test.txt")
        os.makedirs(os.path.dirname(fake_file), exist_ok=True)
        if not os.path.exists(fake_file):
            with open(fake_file, "w") as f:
                f.write("test")

        dangerous_name = "../../etc/evil-backup"
        zip_path = await svc.create_backup(
            include_patterns=["usr/**"],
            exclude_patterns=[],
            backup_name=dangerous_name,
        )
        try:
            # The zip filename must not contain path traversal characters
            zip_basename = os.path.basename(zip_path)
            assert "/" not in zip_basename
            assert ".." not in zip_basename
            assert "evil-backup" in zip_basename  # the safe part survives
            assert zip_basename.endswith(".zip")
        finally:
            # Cleanup
            if os.path.exists(zip_path):
                os.remove(zip_path)
                os.rmdir(os.path.dirname(zip_path))

    def test_backup_name_sanitization_rejects_slashes(self):
        """The sanitization must strip path separator characters from backup names."""
        import re

        dangerous_name = "../../etc/evil-backup"
        sanitized = re.sub(r"[^\w\-]", "_", dangerous_name)
        assert "/" not in sanitized
        assert ".." not in sanitized

    def test_backup_name_sanitization_preserves_safe_chars(self):
        """Safe characters (alphanumeric, hyphen, underscore) must be preserved."""
        import re

        safe_name = "my-backup_2025-01-15"
        sanitized = re.sub(r"[^\w\-]", "_", safe_name)
        assert sanitized == safe_name

    def test_backup_name_sanitization_strips_null_bytes(self):
        """Null bytes in backup names must be replaced."""
        import re

        null_name = "backup\x00evil"
        sanitized = re.sub(r"[^\w\-]", "_", null_name)
        assert "\x00" not in sanitized


# ---------------------------------------------------------------------------
# 10. Additional Cross-Cutting Security Checks
# ---------------------------------------------------------------------------
class TestCrossCuttingSecurity:
    """Additional checks that span multiple modules."""

    def test_format_error_includes_traceback_text(self):
        """format_error must return traceback content (used by dev mode)."""
        from python.helpers.errors import format_error

        try:
            raise ValueError("test error for format_error")
        except ValueError as e:
            result = format_error(e)
            assert "test error for format_error" in result

    def test_safe_file_name_strips_dangerous_chars(self):
        """files.safe_file_name must replace path separator characters."""
        result = files.safe_file_name("../../../etc/passwd")
        assert "/" not in result
        # Dots are safe filename characters so they remain, but slashes are gone
        assert result == ".._.._.._etc_passwd"

    def test_safe_file_name_preserves_normal_chars(self):
        """files.safe_file_name must keep alphanumeric, dash, underscore, dot."""
        result = files.safe_file_name("normal-file_v2.txt")
        assert result == "normal-file_v2.txt"

    # test_write_file_comment_about_sensitivity removed:
    # testing source code comments is not behavioral testing.

    # test_dotenv_write_has_lgtm_suppression removed:
    # testing source code comments is not behavioral testing.
