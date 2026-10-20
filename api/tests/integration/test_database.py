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


def test_reference_tables_seeded() -> None:
    from app.seeds import v1, v2

    _alembic("upgrade", "head")
    with get_engine().connect() as conn:
        counts = {
            table: conn.execute(text(f"SELECT COUNT(*) FROM [core].[{table}]")).scalar_one()
            for table in ("account", "category", "merchant_rule")
        }
    groups = len(v1.CATEGORIES) + sum(1 for g in v2.CATEGORIES if g[2] is not None)
    children = sum(len(g["children"]) for g in v1.CATEGORIES) + sum(
        len(g[3]) for g in v2.CATEGORIES
    )
    assert counts == {
        "account": len(v1.ACCOUNTS),
        "category": groups + children,
        "merchant_rule": len(v1.MERCHANT_RULES),
    }


def test_seed_downgrade_and_reapply() -> None:
    _alembic("downgrade", "0002")
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM [core].[category]")).scalar_one() == 0
    _alembic("upgrade", "head")


def test_excel_history_load_on_sql_server() -> None:
    """Load the synthetic workbook through the API and read exact decimals from the mart views."""
    from decimal import Decimal

    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.fixtures.workbook import build

    _alembic("downgrade", "0003")
    _alembic("upgrade", "head")
    client = TestClient(create_app())
    resp = client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", build(), "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["transactions"] == 13

    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    jan = monthly["2026-01-01"]
    assert Decimal(jan["income"]) == Decimal("8500.25")
    assert Decimal(jan["expenses"]) == Decimal("135.45")
    assert Decimal(jan["net"]) == Decimal("7664.80")
    assert Decimal(jan["cumulative_net"]) == Decimal("9843.90")
    assert Decimal(jan["savings_rate"]) == Decimal("0.9017")

    cats = client.get("/api/cashflow/categories", params={"year": 2026}).json()
    assert {c["group_name"] for c in cats} >= {"Salary", "Health", "Housing", "Savings & Debt"}

    # Loading a second version swaps the rows in one transaction.
    newer = client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", build(lauren_jan_2026=3500), "application/octet-stream")},
    )
    assert newer.json()["replaced_transactions"] == 13

    # Downgrade with data in place, then upgrade again.
    _alembic("downgrade", "0003")
    _alembic("upgrade", "head")
