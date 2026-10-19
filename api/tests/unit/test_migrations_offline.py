"""Renders every migration to SQL without a database, so import or syntax errors in
migrations fail fast in the unit stage (the integration stage runs them for real)."""

import os
import subprocess
import sys

URL = "mssql+pyodbc://sa:x@localhost/cashflow?driver=ODBC+Driver+18+for+SQL+Server"


def _alembic(*args: str) -> str:
    env = {**os.environ, "DATABASE_URL": URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_upgrade_renders_all_stage_schemas() -> None:
    sql = _alembic("upgrade", "head", "--sql")
    for schema in ("raw", "stg", "rej", "core", "mart"):
        assert f"CREATE SCHEMA [{schema}]" in sql
    assert "audit.alembic_version" in sql


def test_downgrade_renders() -> None:
    sql = _alembic("downgrade", "head:base", "--sql")
    assert "DROP SCHEMA [raw]" in sql
