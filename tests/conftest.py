"""Shared pytest fixtures for the test suite.

Provides common fixtures (db_session, _reset_vault_master_key) used across
multiple test modules, eliminating duplication.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from python.helpers.auth_db import Base


@pytest.fixture
def db_session():
    """Provide an in-memory SQLite session with all auth tables created."""
    import python.helpers.audit  # noqa: F401 — register AuditLog on Base
    import python.helpers.user_store  # noqa: F401 — ensure models register on Base

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    _Session = sessionmaker(bind=engine)
    session = _Session()

    yield session

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def _reset_vault_master_key(monkeypatch):
    """Set a test VAULT_MASTER_KEY and reset the cached key between tests."""
    from python.helpers import vault_crypto

    monkeypatch.setenv("VAULT_MASTER_KEY", "a" * 64)
    vault_crypto._master_key = None
    yield
    vault_crypto._master_key = None
