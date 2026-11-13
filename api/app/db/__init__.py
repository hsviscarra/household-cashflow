import logging
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.pool import NullPool

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return make_engine(url)


log = logging.getLogger(__name__)
# Azure SQL serverless pauses when idle; the first login wakes it and can take a minute. These
# errors mean "not awake yet", so the connection is tried again instead of failing (ADR-068).
WAKING = ("40613", "40197", "40501", "HYT00", "Login timeout", "08001", "not currently available")
WAITS = (10, 20, 30)  # seconds between tries, about a minute and a half in all
LOGIN_TIMEOUT = 60  # seconds each try waits for the login


def waking(exc: BaseException) -> bool:
    return any(w in str(exc) for w in WAKING)


def connect_waking(connect: Any, *args: Any, **kw: Any) -> Any:
    """connect(), tried again while the database is waking up; any other error fails at once."""
    for wait in WAITS:
        try:
            return connect(*args, **kw)
        except Exception as exc:
            if not waking(exc):
                raise
            log.warning("database waking up, trying again in %ss: %s", wait, exc)
            time.sleep(wait)
    return connect(*args, **kw)


def make_engine(url: str | URL, **kw: Any) -> Engine:
    """An engine that lets Azure SQL serverless pause and survives its resume: no pooled
    connections on SQL Server, a longer login timeout and a few tries to ride out the resume."""
    mssql = str(url).startswith("mssql")
    if mssql:
        kw.setdefault("connect_args", {}).setdefault("timeout", LOGIN_TIMEOUT)
        # No pool on SQL Server (ADR-092): a pooled connection is an open session, and Azure SQL
        # serverless only pauses with no sessions, so a pool kept the database awake, and
        # billing, for as long as the app was up. A connection per request costs milliseconds.
        kw.setdefault("poolclass", NullPool)
        engine = create_engine(url, **kw)
    else:
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800, **kw)
    if mssql:

        @event.listens_for(engine, "do_connect")
        def _wake(dialect: Any, rec: Any, cargs: Any, cparams: Any) -> Any:
            return connect_waking(dialect.connect, *cargs, **cparams)

    return engine


def get_connection() -> Iterator[Connection]:
    with get_engine().connect() as conn:
        yield conn


def ping(conn: Connection) -> bool:
    return bool(conn.execute(text("SELECT 1")).scalar_one() == 1)
