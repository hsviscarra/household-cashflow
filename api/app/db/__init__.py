from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # pool_pre_ping survives Azure SQL serverless auto-pause/resume.
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def get_connection() -> Iterator[Connection]:
    with get_engine().connect() as conn:
        yield conn


def ping(conn: Connection) -> bool:
    return bool(conn.execute(text("SELECT 1")).scalar_one() == 1)
