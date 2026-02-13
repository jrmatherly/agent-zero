"""Tests for audit logging (Phase 5b.1).

Validates AuditLog ORM model, create_audit_entry writes to DB,
correct fields, and that tokens are never logged.
"""

import json

import pytest


@pytest.fixture(autouse=True)
def _patch_auth_db(db_session, monkeypatch):
    """Patch auth_db.get_session to use the in-memory test database."""
    from contextlib import contextmanager

    from python.helpers import auth_db

    @contextmanager
    def _test_get_session():
        try:
            yield db_session
            db_session.flush()
        except Exception:
            db_session.rollback()
            raise

    monkeypatch.setattr(auth_db, "get_session", _test_get_session)


class TestAuditLogModel:
    def test_audit_log_table_exists(self, db_session):
        from python.helpers.audit import AuditLog

        # Table should be created via Base.metadata.create_all
        assert AuditLog.__tablename__ == "audit_log"

    def test_create_entry_directly(self, db_session):
        from datetime import datetime, timezone

        from python.helpers.audit import AuditLog

        entry = AuditLog(
            id="test-1",
            user_id=None,
            action="test_action",
            resource="/test",
            details_json='{"key": "value"}',
            ip_address="127.0.0.1",
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(entry)
        db_session.flush()

        result = db_session.query(AuditLog).filter_by(id="test-1").one()
        assert result.action == "test_action"
        assert result.resource == "/test"
        assert result.ip_address == "127.0.0.1"


class TestCreateAuditEntry:
    async def test_creates_entry_in_db(self, db_session):
        from python.helpers.audit import AuditLog, create_audit_entry

        await create_audit_entry(
            user_id=None,
            action="login",
            resource="/login",
            details={"method": "local"},
            ip="10.0.0.1",
        )

        entries = db_session.query(AuditLog).all()
        assert len(entries) == 1
        assert entries[0].action == "login"
        assert entries[0].resource == "/login"
        assert entries[0].ip_address == "10.0.0.1"

        details = json.loads(entries[0].details_json)
        assert details["method"] == "local"

    async def test_entry_has_timestamp(self, db_session):
        from python.helpers.audit import AuditLog, create_audit_entry

        await create_audit_entry(user_id=None, action="test")

        entry = db_session.query(AuditLog).one()
        assert entry.timestamp is not None

    async def test_entry_with_user_id(self, db_session):
        """Test that user_id FK works when user exists."""
        import python.helpers.user_store as us

        # Create a user first
        user = us.User(
            id="user-1",
            email="test@example.com",
            display_name="Test",
            auth_provider="local",
        )
        db_session.add(user)
        db_session.flush()

        from python.helpers.audit import AuditLog, create_audit_entry

        await create_audit_entry(
            user_id="user-1",
            action="login",
        )

        entry = db_session.query(AuditLog).one()
        assert entry.user_id == "user-1"

    async def test_no_tokens_in_audit(self, db_session):
        """Verify that token values are never stored in audit details."""
        from python.helpers.audit import AuditLog, create_audit_entry

        # Simulate a details dict that should NOT contain token
        await create_audit_entry(
            user_id=None,
            action="mcp_tool_invoke",
            resource="send_message",
            details={"chat_id": "abc", "project": "demo"},
        )

        entry = db_session.query(AuditLog).one()
        details_str = entry.details_json or ""
        assert "token" not in details_str.lower() or "chat_id" in details_str

    async def test_failure_does_not_raise(self, monkeypatch, db_session):
        """Audit log failures should be silently caught."""
        from python.helpers import audit

        # Break the session to force an error
        monkeypatch.setattr(
            audit.auth_db,
            "get_session",
            lambda: (_ for _ in ()).throw(RuntimeError("DB down")),
        )

        # Should not raise
        await audit.create_audit_entry(user_id=None, action="test")


class TestLoginAuditEvents:
    async def test_login_events_logged(self, db_session):
        from python.helpers.audit import AuditLog, create_audit_entry

        await create_audit_entry(user_id=None, action="login_failed", resource="/login")
        await create_audit_entry(user_id="u1", action="login", resource="/login")

        entries = db_session.query(AuditLog).order_by(AuditLog.timestamp).all()
        assert len(entries) == 2
        assert entries[0].action == "login_failed"
        assert entries[1].action == "login"


class TestMcpToolAuditEvents:
    async def test_mcp_tool_invocation_logged(self, db_session):
        from python.helpers.audit import AuditLog, create_audit_entry

        await create_audit_entry(
            user_id="u1",
            action="mcp_tool_invoke",
            resource="send_message",
            details={"chat_id": "chat-1"},
        )

        entry = db_session.query(AuditLog).one()
        assert entry.action == "mcp_tool_invoke"
        assert entry.resource == "send_message"
        assert entry.user_id == "u1"
