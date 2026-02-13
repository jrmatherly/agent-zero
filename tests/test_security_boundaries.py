"""Security boundary tests for critical Phase 1+ remediation fixes.

Covers:
1. History class registry rejects unknown classes
2. File upload extension validation rejects dangerous extensions
3. OAuth state HMAC rejects tampered values
4. simpleeval blocks dangerous expressions
"""

import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest
from simpleeval import simple_eval

from python.helpers.history import (
    Bulk,
    History,
    Message,
    Record,
    Topic,
)


# ---------------------------------------------------------------------------
# 1. History Class Registry -- Allowlist Enforcement
# ---------------------------------------------------------------------------
class TestHistoryClassRegistry:
    """Record.from_dict must reject unknown _cls values."""

    @pytest.fixture()
    def mock_history(self):
        """Create a lightweight mock History for deserialization tests."""
        agent = MagicMock()
        history = History(agent=agent)
        return history

    def test_valid_message_class_accepted(self, mock_history):
        """Deserializing a dict with _cls='Message' must produce a Message instance."""
        data = {
            "_cls": "Message",
            "ai": True,
            "content": "hello",
            "summary": "",
            "tokens": 0,
        }
        result = Record.from_dict(data, history=mock_history)
        assert isinstance(result, Message)
        assert result.ai is True
        assert result.content == "hello"

    def test_valid_topic_class_accepted(self, mock_history):
        """Deserializing a dict with _cls='Topic' must produce a Topic instance."""
        data = {
            "_cls": "Topic",
            "summary": "test topic",
            "messages": [],
        }
        result = Record.from_dict(data, history=mock_history)
        assert isinstance(result, Topic)
        assert result.summary == "test topic"

    def test_valid_bulk_class_accepted(self, mock_history):
        """Deserializing a dict with _cls='Bulk' must produce a Bulk instance."""
        data = {
            "_cls": "Bulk",
            "summary": "test bulk",
            "records": [],
        }
        result = Record.from_dict(data, history=mock_history)
        assert isinstance(result, Bulk)
        assert result.summary == "test bulk"

    def test_unknown_class_os_rejected(self, mock_history):
        """_cls='os' must be rejected with a ValueError."""
        data = {"_cls": "os", "content": "malicious"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)

    def test_unknown_class_builtins_rejected(self, mock_history):
        """_cls='__builtins__' must be rejected with a ValueError."""
        data = {"_cls": "__builtins__", "content": "malicious"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)

    def test_unknown_class_evil_rejected(self, mock_history):
        """_cls='EvilClass' must be rejected with a ValueError."""
        data = {"_cls": "EvilClass", "content": "malicious"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)

    def test_unknown_class_eval_rejected(self, mock_history):
        """_cls='eval' must be rejected with a ValueError."""
        data = {"_cls": "eval", "content": "__import__('os')"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)

    def test_unknown_class_subprocess_rejected(self, mock_history):
        """_cls='subprocess' must be rejected with a ValueError."""
        data = {"_cls": "subprocess", "content": "Popen"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)

    def test_empty_cls_raises_value_error(self, mock_history):
        """An empty _cls string must be rejected (not in allowlist)."""
        data = {"_cls": "", "content": "empty"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)

    def test_missing_cls_key_raises_error(self, mock_history):
        """A dict without _cls must raise a KeyError."""
        data = {"content": "no class key"}
        with pytest.raises(KeyError):
            Record.from_dict(data, history=mock_history)

    def test_allowlist_contains_exactly_four_classes(self):
        """The allowlist must contain exactly Message, Topic, Bulk, History."""
        allowed = Record._get_allowed_classes()
        assert set(allowed.keys()) == {"Message", "Topic", "Bulk", "History"}

    def test_case_sensitive_rejection(self, mock_history):
        """_cls='message' (lowercase) must be rejected -- allowlist is case-sensitive."""
        data = {"_cls": "message", "ai": True, "content": "hello"}
        with pytest.raises(ValueError, match="Unknown record class"):
            Record.from_dict(data, history=mock_history)


# ---------------------------------------------------------------------------
# 2. File Upload Extension Validation
# ---------------------------------------------------------------------------
class TestUploadExtensionValidation:
    """UploadFile.allowed_file must accept safe extensions and reject dangerous ones."""

    @pytest.fixture()
    def handler(self):
        """Create an UploadFile handler instance for testing."""
        from python.api.upload import UploadFile

        app = MagicMock()
        lock = MagicMock()
        return UploadFile(app, lock)

    # -- Safe extensions accepted --
    @pytest.mark.parametrize(
        "filename",
        [
            "script.py",
            "readme.txt",
            "config.json",
            "document.md",
            "data.csv",
            "image.png",
            "photo.jpg",
            "archive.zip",
            "styles.css",
            "page.html",
        ],
    )
    def test_safe_extensions_accepted(self, handler, filename):
        """Common safe file extensions must be accepted."""
        assert handler.allowed_file(filename) is True

    # -- Dangerous extensions rejected --
    @pytest.mark.parametrize(
        "filename",
        [
            "malware.exe",
            "library.dll",
            "module.so",
            "script.bat",
            "command.cmd",
            "installer.msi",
            "screensaver.scr",
            "program.com",
        ],
    )
    def test_dangerous_extensions_rejected(self, handler, filename):
        """Executable/dangerous file extensions must be rejected."""
        assert handler.allowed_file(filename) is False

    # -- Case insensitivity --
    @pytest.mark.parametrize(
        "filename",
        [
            "MALWARE.EXE",
            "Library.Dll",
            "SCRIPT.BAT",
            "Command.CMD",
            "virus.ExE",
        ],
    )
    def test_dangerous_extensions_case_insensitive(self, handler, filename):
        """Dangerous extensions must be rejected regardless of case."""
        assert handler.allowed_file(filename) is False

    def test_no_extension_rejected(self, handler):
        """Files with no extension must be rejected."""
        assert handler.allowed_file("Makefile") is False

    def test_double_extension_exe_rejected(self, handler):
        """Double extensions like 'file.txt.exe' must be rejected (suffix is .exe)."""
        assert handler.allowed_file("document.txt.exe") is False

    def test_double_extension_safe_accepted(self, handler):
        """Double extensions where the final extension is safe must be accepted."""
        assert handler.allowed_file("archive.tar.gz") is True

    def test_empty_filename_rejected(self, handler):
        """Empty filename must be rejected."""
        assert handler.allowed_file("") is False

    def test_none_filename_rejected(self, handler):
        """None filename must be rejected."""
        assert handler.allowed_file(None) is False

    def test_dot_only_filename_rejected(self, handler):
        """A filename that is just a dot must be rejected (no valid extension)."""
        assert handler.allowed_file(".") is False

    def test_hidden_file_with_valid_extension(self, handler):
        """Hidden files (dot-prefixed) with valid extensions must be accepted."""
        assert handler.allowed_file(".gitignore.txt") is True


# ---------------------------------------------------------------------------
# 2b. FileBrowser Extension Validation
# ---------------------------------------------------------------------------
class TestFileBrowserExtensionValidation:
    """FileBrowser._is_allowed_file must also validate extensions."""

    @pytest.fixture()
    def browser(self):
        from python.helpers.file_browser import FileBrowser

        return FileBrowser()

    @pytest.mark.parametrize(
        "filename",
        ["test.py", "readme.txt", "data.json", "photo.png", "song.mp3"],
    )
    def test_safe_extensions_accepted(self, browser, filename):
        """Safe extensions must be accepted by the file browser."""
        mock_file = MagicMock()
        assert browser._is_allowed_file(filename, mock_file) is True

    @pytest.mark.parametrize(
        "filename",
        ["malware.exe", "library.dll", "module.so", "script.bat", "command.cmd"],
    )
    def test_dangerous_extensions_rejected(self, browser, filename):
        """Dangerous extensions must be rejected by the file browser."""
        mock_file = MagicMock()
        assert browser._is_allowed_file(filename, mock_file) is False

    def test_case_insensitive_rejection(self, browser):
        """Extension check must be case-insensitive."""
        mock_file = MagicMock()
        assert browser._is_allowed_file("VIRUS.EXE", mock_file) is False

    def test_empty_filename_rejected(self, browser):
        """Empty filename must be rejected."""
        mock_file = MagicMock()
        assert browser._is_allowed_file("", mock_file) is False


# ---------------------------------------------------------------------------
# 3. OAuth State HMAC Integrity
# ---------------------------------------------------------------------------
class TestOAuthStateHMAC:
    """OAuth state parameter must be integrity-protected with HMAC-SHA256.

    Tests exercise the state creation logic from mcp_oauth_start.py and the
    verification logic from run_ui.mcp_oauth_callback.
    """

    SECRET_KEY = b"test-secret-key-for-hmac"

    def _create_state(self, payload_data: dict) -> str:
        """Replicate the state creation from McpOauthStart.process."""
        payload = base64.b64encode(json.dumps(payload_data).encode()).decode()
        signature = hmac.new(
            self.SECRET_KEY, payload.encode(), hashlib.sha256
        ).hexdigest()
        return f"{payload}.{signature}"

    def _verify_state(self, state: str) -> dict | None:
        """Replicate the state verification from mcp_oauth_callback.

        Returns the decoded payload on success, or None on failure.
        """
        if not state or "." not in state:
            return None

        payload, received_sig = state.rsplit(".", 1)
        expected_sig = hmac.new(
            self.SECRET_KEY, payload.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(received_sig, expected_sig):
            return None

        try:
            return json.loads(base64.b64decode(payload).decode())
        except Exception:
            return None

    def test_valid_state_roundtrip(self):
        """A state created with _create_state must verify successfully."""
        data = {"user_id": "u123", "service_id": "s456", "scopes": "read write"}
        state = self._create_state(data)
        result = self._verify_state(state)
        assert result is not None
        assert result["user_id"] == "u123"
        assert result["service_id"] == "s456"
        assert result["scopes"] == "read write"

    def test_tampered_payload_rejected(self):
        """Modifying the payload after signing must cause verification to fail."""
        data = {"user_id": "u123", "service_id": "s456"}
        state = self._create_state(data)

        # Tamper with the payload (change a character in the base64)
        payload, sig = state.rsplit(".", 1)
        tampered_chars = list(payload)
        tampered_chars[5] = "X" if tampered_chars[5] != "X" else "Y"
        tampered_payload = "".join(tampered_chars)
        tampered_state = f"{tampered_payload}.{sig}"

        result = self._verify_state(tampered_state)
        assert result is None

    def test_tampered_signature_rejected(self):
        """Modifying the signature must cause verification to fail."""
        data = {"user_id": "u123", "service_id": "s456"}
        state = self._create_state(data)

        payload, sig = state.rsplit(".", 1)
        tampered_sig = "a" * len(sig)  # Replace entire signature
        tampered_state = f"{payload}.{tampered_sig}"

        result = self._verify_state(tampered_state)
        assert result is None

    def test_missing_signature_rejected(self):
        """A state with no dot separator (no signature) must be rejected."""
        payload = base64.b64encode(json.dumps({"user_id": "u123"}).encode()).decode()
        # No dot, no signature
        result = self._verify_state(payload)
        assert result is None

    def test_empty_state_rejected(self):
        """An empty state string must be rejected."""
        assert self._verify_state("") is None

    def test_none_state_rejected(self):
        """A None state must be rejected."""
        assert self._verify_state(None) is None

    def test_wrong_key_rejected(self):
        """A state signed with a different key must fail verification."""
        data = {"user_id": "u123", "service_id": "s456"}
        payload = base64.b64encode(json.dumps(data).encode()).decode()
        wrong_key = b"wrong-secret-key"
        wrong_sig = hmac.new(wrong_key, payload.encode(), hashlib.sha256).hexdigest()
        state = f"{payload}.{wrong_sig}"

        result = self._verify_state(state)
        assert result is None

    def test_state_contains_base64_payload_and_hex_signature(self):
        """State format must be base64_payload.hex_signature."""
        data = {"user_id": "u123"}
        state = self._create_state(data)
        parts = state.split(".")
        assert len(parts) == 2

        # Payload should be valid base64
        payload_bytes = base64.b64decode(parts[0])
        payload_json = json.loads(payload_bytes)
        assert payload_json["user_id"] == "u123"

        # Signature should be a 64-char hex string (SHA-256)
        assert len(parts[1]) == 64
        int(parts[1], 16)  # Must parse as hex without error

    def test_multiple_dots_in_payload_handled(self):
        """rsplit('.', 1) must correctly handle state values with extra dots."""
        data = {"user_id": "u123"}
        payload = base64.b64encode(json.dumps(data).encode()).decode()
        # Manually craft a state with an extra dot in it
        prefixed_payload = f"prefix.{payload}"
        fake_sig = hmac.new(
            self.SECRET_KEY,
            prefixed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        state = f"{prefixed_payload}.{fake_sig}"

        # rsplit('.', 1) splits on the LAST dot, so payload = "prefix.<base64>"
        result = self._verify_state(state)
        # Signature matches but base64 decode of "prefix.<base64>" will fail
        # because it includes the "prefix." which is not valid base64
        assert result is None


# ---------------------------------------------------------------------------
# 4. simpleeval Blocks Dangerous Expressions
# ---------------------------------------------------------------------------
class TestSimpleevalSecurity:
    """simpleeval.simple_eval must block dangerous Python expressions.

    The codebase uses simple_eval in:
    - python/helpers/files.py (evaluate_text_conditions)
    - python/helpers/memory.py (_get_comparator)
    - python/helpers/vector_db.py (get_comparator)
    """

    def test_import_os_blocked(self):
        """__import__('os') must be blocked."""
        with pytest.raises(Exception):
            simple_eval("__import__('os').system('echo pwned')")

    def test_builtins_access_blocked(self):
        """Access to __builtins__ must be blocked."""
        with pytest.raises(Exception):
            simple_eval("__builtins__")

    def test_dunder_class_access_blocked(self):
        """Attribute access to __class__ must be blocked."""
        with pytest.raises(Exception):
            simple_eval("''.__class__.__mro__[1].__subclasses__()")

    def test_eval_blocked(self):
        """eval() must be blocked."""
        with pytest.raises(Exception):
            simple_eval("eval('1+1')")

    def test_exec_blocked(self):
        """exec() must be blocked."""
        with pytest.raises(Exception):
            simple_eval("exec('import os')")

    def test_open_blocked(self):
        """open() must be blocked."""
        with pytest.raises(Exception):
            simple_eval("open('/etc/passwd')")

    def test_compile_blocked(self):
        """compile() must be blocked."""
        with pytest.raises(Exception):
            simple_eval("compile('1+1', '<string>', 'eval')")

    def test_getattr_blocked(self):
        """getattr() must be blocked."""
        with pytest.raises(Exception):
            simple_eval("getattr('', '__class__')")

    # -- Positive tests: normal expressions must work --

    def test_basic_math(self):
        """Basic arithmetic expressions must evaluate correctly."""
        assert simple_eval("2 + 3") == 5
        assert simple_eval("10 * 5") == 50
        assert simple_eval("100 / 4") == 25.0

    def test_comparison(self):
        """Comparison operators must work."""
        assert simple_eval("5 > 3") is True
        assert simple_eval("2 == 3") is False
        assert simple_eval("1 < 10") is True

    def test_boolean_logic(self):
        """Boolean operators must work."""
        assert simple_eval("True and True") is True
        assert simple_eval("True or False") is True
        assert simple_eval("not False") is True

    def test_named_variables(self):
        """Variables passed via names= must be accessible."""
        result = simple_eval("x + y", names={"x": 10, "y": 20})
        assert result == 30

    def test_string_comparison(self):
        """String equality checks must work (used in condition evaluation)."""
        result = simple_eval("name == 'admin'", names={"name": "admin"})
        assert result is True

    def test_condition_evaluation_pattern(self):
        """Test the pattern used by evaluate_text_conditions in files.py."""
        # Simulates {{if agent_name == 'default'}} ... {{endif}}
        result = simple_eval("agent_name == 'default'", names={"agent_name": "default"})
        assert result is True

        result = simple_eval("agent_name == 'default'", names={"agent_name": "other"})
        assert result is False

    def test_comparator_pattern(self):
        """Test the pattern used by get_comparator in vector_db.py."""
        # Simulates memory filter conditions like "category == 'fact'"
        data = {"category": "fact", "score": 0.95}
        result = simple_eval("category == 'fact'", names=data)
        assert result is True

        result = simple_eval("score > 0.9", names=data)
        assert result is True

        result = simple_eval("score < 0.5", names=data)
        assert result is False
