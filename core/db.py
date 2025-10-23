from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from .alembic_utils import ensure_up_to_date
from .models import Base
from .settings import get_settings

# Module-level singletons
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_ScopedSession: Optional[scoped_session] = None


logger = logging.getLogger("payroll_core.db")


def _resolve_database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        return settings.database_url
    # Default to a repo-local SQLite database for developer convenience.
    root = Path(__file__).resolve().parents[1]
    db_path = (root / "payroll_portal" / "app.db").resolve()
    return f"sqlite:///{db_path}"


def get_engine(echo: bool = False) -> Engine:
    """Return a singleton SQLAlchemy engine."""
    global _engine
    if _engine is None:
        database_url = _resolve_database_url()
        url = make_url(database_url)
        connect_args = {}
        if url.get_backend_name() == "sqlite":
            connect_args = {"check_same_thread": False}
            logger.warning(
                "SQLite 백엔드를 사용 중입니다. 운영 환경에서는 PostgreSQL 같은 외부 DB 사용을 권장합니다."
            )
        _engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)
        if url.get_backend_name() == "sqlite":
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[unused-argument]
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    cursor.execute("PRAGMA synchronous=NORMAL;")
                    cursor.execute("PRAGMA foreign_keys=ON;")
                finally:
                    cursor.close()
            logger.debug("SQLite 엔진 초기화: WAL 모드 및 foreign_keys 활성화")
    return _engine


def get_sessionmaker() -> sessionmaker:
    """Return the global sessionmaker instance."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine(), future=True)
    return _SessionLocal


def get_scoped_session() -> scoped_session:
    """Return a scoped_session factory for frameworks that expect thread-local sessions."""
    global _ScopedSession
    if _ScopedSession is None:
        _ScopedSession = scoped_session(get_sessionmaker())
    return _ScopedSession


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fastapi_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def init_database(auto_apply_ddl: Optional[bool] = None, enforce_alembic: Optional[bool] = None) -> Engine:
    """Ensure the database is ready and return the engine."""
    engine = get_engine()
    settings = get_settings()

    auto = settings.payroll_auto_apply_ddl if auto_apply_ddl is None else auto_apply_ddl
    enforce = settings.enforce_alembic_migrations if enforce_alembic is None else enforce_alembic

    if auto:
        Base.metadata.create_all(bind=engine)
    elif enforce:
        ensure_up_to_date(engine)

    return engine
