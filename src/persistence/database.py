from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from src.config import _int_env, get_settings

_engine: Engine | None = None
_engine_url: str | None = None
_SessionLocal: sessionmaker | None = None


def get_database_url() -> str | None:
    url = get_settings().database_url
    if not url:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    override = os.environ.get("POSTGRES_HOST_OVERRIDE", "").strip()
    if override:
        parsed = make_url(url).set(host=override)
        url = parsed.render_as_string(hide_password=False)
    return url


def reset_engine() -> None:
    global _engine, _engine_url, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
    _SessionLocal = None


def get_engine() -> Engine | None:
    """Return a pooled PostgreSQL engine. Never drops or recreates user data."""
    global _engine, _engine_url, _SessionLocal
    url = get_database_url()
    if not url:
        return None
    if _engine is not None and _engine_url != url:
        reset_engine()
    if _engine is None:
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=_int_env("DB_POOL_SIZE", 5, minimum=1, maximum=20),
            max_overflow=_int_env("DB_MAX_OVERFLOW", 5, minimum=0, maximum=20),
            pool_timeout=_int_env("DB_POOL_TIMEOUT_SECONDS", 10, minimum=1, maximum=60),
            pool_recycle=_int_env("DB_POOL_RECYCLE_SECONDS", 1800, minimum=30, maximum=7200),
            connect_args={
                "connect_timeout": _int_env("DB_CONNECT_TIMEOUT_SECONDS", 5, minimum=1, maximum=30)
            },
            future=True,
        )
        _engine_url = url
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

        @event.listens_for(_engine, "connect")
        def _set_postgres_timeouts(dbapi_connection, _connection_record) -> None:
            if _engine is None or _engine.dialect.name != "postgresql":
                return
            statement_ms = _int_env("DB_STATEMENT_TIMEOUT_MS", 15000, minimum=1000, maximum=120000)
            lock_ms = _int_env("DB_LOCK_TIMEOUT_MS", 5000, minimum=100, maximum=60000)
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"SET statement_timeout = {int(statement_ms)}")
                cursor.execute(f"SET lock_timeout = {int(lock_ms)}")
            finally:
                cursor.close()

    return _engine


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        get_engine()
    if _SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_postgres_configured() -> bool:
    return get_database_url() is not None
