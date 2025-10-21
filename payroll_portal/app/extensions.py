from __future__ import annotations

import os
from typing import Optional

from flask import current_app
from redis import Redis  # type: ignore
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from payroll_shared.alembic_utils import ensure_up_to_date
from payroll_shared.models import Base
from payroll_shared.settings import get_settings

def init_database(app) -> None:
    settings = get_settings()
    db_url = settings.database_url
    if not db_url:
        base_dir = os.path.abspath(os.path.join(app.root_path, "..", ".."))
        db_path = os.path.join(base_dir, "payroll_portal", "app.db")
        db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=False, future=True)
    session_factory = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    )
    app.extensions["sqlalchemy_session"] = session_factory
    app.extensions["engine"] = engine
    app.config.setdefault("DATABASE_URL", db_url)

    if settings.payroll_auto_apply_ddl:
        Base.metadata.create_all(engine)
    elif settings.enforce_alembic_migrations:
        ensure_up_to_date(engine)


def init_redis(app) -> None:
    url = (
        os.environ.get("LOCK_REDIS_URL")
        or os.environ.get("REDIS_URL")
        or os.environ.get("ADMIN_RATE_LIMIT_REDIS_URL")
    )
    if not url:
        app.extensions["redis_client"] = None
        return
    try:
        client = Redis.from_url(url, decode_responses=True)
        app.extensions["redis_client"] = client
    except Exception:
        app.extensions["redis_client"] = None


def init_extensions(app) -> None:
    init_database(app)
    init_redis(app)


def db_session(app=None):
    app = app or current_app
    session_factory = app.extensions.get("sqlalchemy_session")
    if session_factory is None:  # pragma: no cover
        raise RuntimeError("Database session not initialized")
    return session_factory


def redis_client(app=None) -> Optional[Redis]:
    app = app or current_app
    return app.extensions.get("redis_client")
