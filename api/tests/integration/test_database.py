"""Runs against a real SQL Server (the CI service container or docker compose).

DATABASE_URL=... uv run pytest -m integration
"""

import subprocess

import pytest
from sqlalchemy import text

from app.db import get_engine
from app.routers.health import database_check

pytestmark = pytest.mark.integration

STAGE_SCHEMAS = {"raw", "stg", "rej", "core", "mart"}


def _schemas() -> set[str]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT [name] FROM [sys].[schemas]")).scalars()
        return set(rows)


def _alembic(*args: str) -> None:
    subprocess.run(["alembic", *args], check=True)


def test_database_check_succeeds() -> None:
    assert database_check()() is True


def test_migrations_upgrade_and_downgrade() -> None:
    _alembic("upgrade", "head")
    assert {*STAGE_SCHEMAS, "audit"} <= _schemas()
    _alembic("downgrade", "base")
    assert not STAGE_SCHEMAS & _schemas()
    _alembic("upgrade", "head")
    assert _schemas() >= STAGE_SCHEMAS
