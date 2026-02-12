"""Database engine and session factory for the auth system.

Provides a database-agnostic (SQLite + PostgreSQL) persistence layer
using SQLAlchemy 2.0 declarative base, engine initialization, and a
context-managed session with automatic commit/rollback.

Configuration:
    AUTH_DATABASE_URL env var (default: ``sqlite:///usr/auth.db``)
"""

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from python.helpers.print_style import PrintStyle

# ---------------------------------------------------------------------------
# Declarative base — imported by model modules (e.g. user_store.py)
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all auth-system ORM models."""


# ---------------------------------------------------------------------------
# Module-level engine / session factory (initialized lazily via init_db)
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

_DEFAULT_URL = "sqlite:///usr/auth.db"


def init_db(url: str | None = None) -> None:
    """Initialize the auth database engine and session factory.

    Args:
        url: SQLAlchemy connection string.  Falls back to the
            ``AUTH_DATABASE_URL`` env var, then to the built-in default
            (``sqlite:///usr/auth.db``).
    """
    global _engine, _SessionLocal

    url = url or os.environ.get("AUTH_DATABASE_URL", _DEFAULT_URL)

    connect_args: dict = {}
    if url.startswith("sqlite"):
        # SQLite is not thread-safe by default; allow multi-threaded access
        connect_args["check_same_thread"] = False

    _engine = create_engine(url, echo=False, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine)

    PrintStyle.info(f"Auth database initialized ({url.split('://')[0]} backend)")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager yielding a SQLAlchemy session.

    Commits on clean exit, rolls back on exception, and always closes
    the session.

    Raises:
        RuntimeError: If :func:`init_db` has not been called yet.
    """
    if _SessionLocal is None:
        raise RuntimeError(
            "Auth database not initialized. Call init_db() before requesting a session."
        )

    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
