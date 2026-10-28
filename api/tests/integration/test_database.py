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
    from app.seeds import v1, v2, v3, v4

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
        "account": len(v1.ACCOUNTS) + len(v3.ACCOUNTS),
        "category": groups + children,
        "merchant_rule": len(v1.MERCHANT_RULES) + len(v3.MERCHANT_RULES) + len(v4.MERCHANT_RULES),
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


def test_statement_upload_on_sql_server(tmp_path: object) -> None:
    """Upload synthetic statements through the API against SQL Server, re-upload, downgrade."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("bofa.pdf", s.bofa(), "application/pdf"))]
    first = client.post("/api/statements", files=files).json()[0]
    assert first["outcome"] == "stored", first
    assert sorted(a["last4"] for a in first["statement"]["accounts"]) == ["1862", "8872"]
    assert client.post("/api/statements", files=files).json()[0]["outcome"] == "duplicate"

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")


def test_capital_one_read_and_approve_on_sql_server(tmp_path: object) -> None:
    """Read, tie out and approve a synthetic Capital One statement on SQL Server."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM [core].[transaction] WHERE [source] = 'statement'"))
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("co.pdf", s.capitalone_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b["tieout_ok"] is True, b["checks"]
    ok = client.post(f"/api/batches/{b['batch_id']}/approve").json()
    assert ok["loaded"] == 11
    monthly = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    assert Decimal(monthly["2026-09-01"]["expenses"]) == Decimal("256.75")

    # Downgrade with loaded statement lines, then upgrade again.
    _alembic("downgrade", "0005")
    _alembic("upgrade", "head")


def test_pacificard_source_and_guarded_downgrade(tmp_path: object) -> None:
    """Migration 0009 accepts the new source; its downgrade refuses while such statements exist."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion import ocr
    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    if not ocr.available():
        pytest.skip("tesseract is not installed")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("pc.pdf", s.pacificard_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    assert st["source"] == "pacificard"
    assert st["accounts"][0]["name"] == "Pacificard Mastercard Black"

    with pytest.raises(subprocess.CalledProcessError):
        _alembic("downgrade", "0008")
    with get_engine().begin() as conn:
        ids = "SELECT [statement_file_id] FROM [raw].[statement_file] WHERE [source] = 'pacificard'"
        conn.execute(
            text(f"DELETE FROM [raw].[statement_file_account] WHERE [statement_file_id] IN ({ids})")
        )
        conn.execute(text("DELETE FROM [raw].[statement_file] WHERE [source] = 'pacificard'"))
    _alembic("downgrade", "0008")
    _alembic("upgrade", "head")


def test_classification_on_sql_server(tmp_path: object) -> None:
    """F9 on SQL Server: resolve with a rule, split (views count the parts), guarded downgrade."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    # Start from empty statement tables: an earlier test loaded the same synthetic statement.
    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM [core].[transaction] WHERE [source] = 'statement'"))
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("co9.pdf", s.capitalone_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b.get("tieout_ok") is True, b
    client.post(f"/api/batches/{b['batch_id']}/approve")

    review = client.get("/api/review", params={"month": "2026-10-01"}).json()
    group = next(g for g in review["groups"] if g["merchant_key"].startswith("NEW MERCHANT"))
    cats = client.get("/api/categories").json()
    travel = next(c["category_id"] for c in cats if c["name"] == "Travel")
    done = client.post(
        "/api/review/resolve",
        json={"merchant_key": group["merchant_key"], "category_id": travel, "save_rule": True},
    ).json()
    assert done["categorized"] == 1 and done["rule_id"]

    txns = client.get("/api/transactions", params={"month": "2026-09-01"}).json()
    uber = next(t for t in txns if t["amount"] == "-12.5000")
    groceries = next(c for c in cats if c["name"] == "Groceries")["children"][0]["category_id"]
    url = f"/api/transactions/{uber['transaction_id']}/split"
    before = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    parts = [
        {"amount": "-10.00", "category_id": groceries},
        {"amount": "-2.50", "category_id": travel},
    ]
    assert len(client.put(url, json={"parts": parts}).json()) == 2
    after = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    # Same total, one more line counted (two parts replace one line).
    assert after["2026-09-01"]["expenses"] == before["2026-09-01"]["expenses"]
    assert after["2026-09-01"]["transactions"] == before["2026-09-01"]["transactions"] + 1
    assert Decimal(after["2026-09-01"]["expenses"]) > 0

    with pytest.raises(subprocess.CalledProcessError):
        _alembic("downgrade", "0009")
    assert client.delete(url).status_code == 204
    _alembic("downgrade", "0009")
    _alembic("upgrade", "head")


def test_transfers_and_cash_view_on_sql_server(tmp_path: object) -> None:
    """F10 on SQL Server: own-account transfer matched on approve, both views, 0011 down and up."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("bofa10.pdf", s.bofa_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b.get("tieout_ok") is True, b
    client.post(f"/api/batches/{b['batch_id']}/approve")

    aug = client.get("/api/transactions", params={"month": "2026-08-01"}).json()
    legs = [t for t in aug if t["amount"] in ("-25.0000", "25.0000")]
    assert len({t["transfer_group_id"] for t in legs}) == 1 and legs[0]["transfer_with"]

    cash = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly?view=cash").json()}
    spend = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    # August: the Capital One payment from checking is cash out as a card payment, not spending.
    assert Decimal(cash["2026-08-01"]["card_payments"]) == Decimal("1500")
    assert Decimal(spend["2026-08-01"]["card_payments"]) == 0

    _alembic("downgrade", "0010")
    _alembic("upgrade", "head")


def test_recurring_on_sql_server(tmp_path: object) -> None:
    """F11 on SQL Server: templates from the workbook, the grid, statement matching, 0012 down
    and up with linked lines."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s
    from tests.fixtures.workbook import build

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    loaded = client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", build(lauren_jan_2026=3111), xlsx)},
    )
    assert loaded.status_code == 200, loaded.text
    names = ["Lauren", "Hernan (Salaries)", "Interactive Brokers"]
    made = client.post("/api/recurring/from-excel", json={"year": 2026, "names": names}).json()
    assert made == {"templates": 3, "entries": 6, "linked": 3}
    grid = {r["name"]: r for r in client.get("/api/recurring/grid?year=2026").json()["rows"]}
    assert Decimal(grid["Lauren"]["cells"][0]["actual"]) == Decimal("3111")
    assert grid["Lauren"]["cells"][6]["status"] == "planned"

    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    accounts = {a["name"]: a for a in client.get("/api/accounts").json()}
    own = next(
        ch
        for c in cats.values()
        for ch in c.get("children", [])
        if ch["name"] == "Between Own Accounts"
    )
    created = client.post(
        "/api/recurring/templates",
        json={
            "name": "To savings",
            "category_id": own["category_id"],
            "type": "transfer",
            "amount": "25",
            "start_month": "2026-08-01",
            "account_id": accounts["BofA Regular Savings"]["account_id"],
        },
    )
    assert created.status_code == 201, created.text
    client.post("/api/recurring/generate", json={"month": "2026-08-01"})
    files = [("files", ("bofa11.pdf", s.bofa_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    if b.get("batch_id"):
        client.post(f"/api/batches/{b['batch_id']}/approve")
    client.post("/api/recurring/match")
    grid = {r["name"]: r for r in client.get("/api/recurring/grid?year=2026").json()["rows"]}
    assert grid["To savings"]["cells"][7]["status"] == "matched"
    # Change from month X filters on is_override (a BIT): "= 0", not "IS 0", on SQL Server.
    tid = grid["To savings"]["template_id"]
    changed = client.post(
        f"/api/recurring/templates/{tid}/amount", json={"from_month": "2026-08-01", "amount": "30"}
    )
    assert changed.status_code == 200, changed.text

    _alembic("downgrade", "0011")
    _alembic("upgrade", "head")


def test_month_status_on_sql_server(tmp_path: object) -> None:
    """F12 on SQL Server: coverage by day, the load log and pending imports."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("bofa12.pdf", s.bofa_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    if b.get("batch_id") and b.get("tieout_ok"):
        client.post(f"/api/batches/{b['batch_id']}/approve")
    status = client.get("/api/status", params={"today": "2026-08-31"}).json()
    names = {a["account_id"]: a["name"] for a in status["accounts"]}
    aug = next(m for m in status["months"] if m["month"] == "2026-08-01")
    cover = {names[c["account_id"]]: c["state"] for c in aug["coverage"]}
    assert cover["BofA Adv Plus Banking"] in ("full", "partial")
    assert cover["Capital One Venture"] == "none"
    assert any(i["text"].startswith("Capital One Venture: no statement") for i in aug["items"])
    assert any(load["source"] == "statement" for load in status["loads"])


def test_spending_on_sql_server(tmp_path: object) -> None:
    """F13 on SQL Server: mart.v_spending_line totals equal the spending view; drill-down; 0013
    down and up."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("bofa13.pdf", s.bofa_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    if b.get("batch_id") and b.get("tieout_ok"):
        client.post(f"/api/batches/{b['batch_id']}/approve")
    out = client.get("/api/spending", params={"month": "2026-08-01"}).json()
    overview = {m["cash_month"]: m for m in client.get("/api/cashflow/monthly").json()}
    assert Decimal(out["total"]["amount"]) == Decimal(overview["2026-08-01"]["expenses"])
    assert out["groups"] and len(out["trend"]) == 12
    group = out["groups"][0]
    lines = client.get(
        "/api/spending/lines", params={"month": "2026-08-01", "group_id": group["group_id"]}
    ).json()
    assert sum(Decimal(ln["amount"]) for ln in lines) == Decimal(group["amount"])
    fixed = client.get("/api/spending/lines", params={"month": "2026-08-01", "fixed": "false"})
    assert fixed.status_code == 200

    _alembic("downgrade", "0012")
    _alembic("upgrade", "head")


def test_subscriptions_and_debt_on_sql_server(tmp_path: object) -> None:
    """F14 on SQL Server: Capital One interest year to date from mart.v_debt_cost, its balance,
    the subscriptions endpoint; 0014 down and up."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    # Statement lines from earlier tests survive the downgrade (core.transaction is older than
    # 0005); clear them so this test's interest is its own.
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM [core].[transaction] WHERE [parent_transaction_id] IS NOT NULL")
        )
        conn.execute(text("DELETE FROM [core].[transaction] WHERE [source] <> 'excel_history'"))
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("co14.pdf", s.capitalone_full(interest="12.34"), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    assert b.get("tieout_ok") is True, b
    client.post(f"/api/batches/{b['batch_id']}/approve")
    debt = client.get("/api/debt", params={"year": 2026, "today": "2026-10-27"}).json()
    co = next(a for a in debt["accounts"] if a["name"] == "Capital One Venture")
    assert Decimal(co["interest"]) == Decimal("12.34")
    assert co["balance_date"] == "2026-10-03"
    subs = client.get("/api/subscriptions", params={"today": "2026-10-27"})
    assert subs.status_code == 200, subs.text

    _alembic("downgrade", "0013")
    _alembic("upgrade", "head")


def test_balance_sheet_on_sql_server(tmp_path: object) -> None:
    """F14 balance sheet on SQL Server: values entered on the page, the balance sheet; 0015 down
    (page values go) and up again, when its data step turns the workbook's balances into
    holdings."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures.workbook import build

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    client.post(
        "/api/history/excel/load",
        files={"file": ("Cash Flow.xlsx", build(lauren_jan_2026=3015), xlsx)},
    )
    created = client.post(
        "/api/holdings",
        json={
            "name": "Office",
            "holding_class": "property",
            "value": "60000",
            "as_of": "2026-01-01",
        },
    )
    assert created.status_code == 201, created.text
    sheet = client.get("/api/networth", params={"as_of": "2026-10-27"}).json()
    names = {i["name"]: i for i in sheet["items"]}
    assert Decimal(names["Office"]["value"]) == Decimal("60000")
    assert names["BIESS"]["holding_class"] == "loan"
    assert Decimal(sheet["net_worth"]) == Decimal(sheet["assets"]) - Decimal(sheet["liabilities"])

    _alembic("downgrade", "0014")
    _alembic("upgrade", "head")
    with get_engine().connect() as conn:
        rows = dict(
            conn.execute(
                text(
                    "SELECT [h].[name], [h].[holding_class] FROM [core].[holding] AS [h] "
                    "WHERE EXISTS (SELECT 1 FROM [core].[balance_snapshot] AS [s] "
                    "WHERE [s].[holding_id] = [h].[holding_id])"
                )
            ).all()
        )
    assert rows["BIESS"] == "loan" and rows["Stock Market"] == "investment"
    assert "Office" not in rows


def test_projections_on_sql_server(tmp_path: object) -> None:
    """F15 on SQL Server: the projection's queries (the spending view joined to transactions and
    accounts, recurring entries, holdings) run, with cash from a statement."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    files = [("files", ("bofa15.pdf", s.bofa_full(), "application/pdf"))]
    st = client.post("/api/statements", files=files).json()[0]["statement"]
    b = client.post(f"/api/statements/{st['statement_file_id']}/read").json()
    if b.get("batch_id") and b.get("tieout_ok"):
        client.post(f"/api/batches/{b['batch_id']}/approve")
    resp = client.get("/api/projections", params={"today": "2026-10-20"})
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert Decimal(p["start_cash"]) > 0
    assert [m["month"] for m in p["months"]] == ["2026-11-01", "2026-12-01", "2027-01-01"]
    assert p["daily"][-1]["day"] == "2027-01-31"


def test_loan_schedule_on_sql_server(tmp_path: object) -> None:
    """F14 loan table on SQL Server: upload, the balance and summary, the payment check, the
    projected installment; 0016 down (installments and the table's balances go) and up."""
    from decimal import Decimal
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures import statements as s

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    with get_engine().connect() as conn:
        cat = conn.execute(
            text("SELECT [category_id] FROM [core].[category] WHERE [name] = 'Mortgage BIESS'")
        ).scalar_one()
    template = client.post(
        "/api/recurring/templates",
        json={
            "name": "Mortgage",
            "category_id": cat,
            "type": "expense",
            "amount": "1100",
            "start_month": "2026-01-01",
        },
    ).json()["template_id"]
    hid = client.post(
        "/api/holdings",
        json={
            "name": "Mortgage",
            "holding_class": "loan",
            "recurring_template_id": template,
            "value": "12000",
            "as_of": "2025-12-31",
        },
    ).json()["holding_id"]
    up = client.post(
        f"/api/holdings/{hid}/schedule",
        files={"file": ("t.pdf", s.loan_table(), "application/pdf")},
    )
    assert up.status_code == 200, up.text
    items = client.get("/api/networth", params={"as_of": "2026-10-27"}).json()["items"]
    loan = next(i for i in items if i["name"] == "Mortgage")
    assert Decimal(loan["value"]) == 2000 and loan["loan"]["schedule"]["left"] == 2
    pays = client.get(f"/api/holdings/{hid}/payments", params={"today": "2026-10-27"})
    assert pays.status_code == 200 and len(pays.json()) == 12
    proj = client.get("/api/projections", params={"today": "2026-10-27"}).json()
    nov = next(e for e in proj["months"][0]["items"] if e["name"] == "Mortgage")
    assert Decimal(nov["amount"]) == Decimal("-1022.5")

    _alembic("downgrade", "0015")
    with get_engine().connect() as conn:
        left = conn.execute(
            text("SELECT COUNT(*) FROM [core].[balance_snapshot] WHERE [source] = 'amortization'")
        ).scalar_one()
    assert left == 0
    _alembic("upgrade", "head")


def test_report_and_exports_on_sql_server(tmp_path: object) -> None:
    """F16 on SQL Server: a report generated (rules) and saved from the workbook's months, the
    exports in both formats; 0017 down and up."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from tests.fixtures.workbook import build

    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)))
    client = TestClient(app)
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    client.post("/api/history/excel/load", files={"file": ("Cash Flow.xlsx", build(), xlsx)})
    month = client.get("/api/reports").json()["months"][0][:7]
    resp = client.post(f"/api/reports/{month}/generate", params={"today": "2026-10-28"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["written_by"] == "rules" and len(resp.json()["findings"]) >= 1
    assert client.get(f"/api/reports/{month}").json()["month"][:7] == month
    for key in ("monthly_cashflow", "monthly_cash", "category_month", "spending_lines"):
        for fmt in ("csv", "xlsx"):
            got = client.get(f"/api/exports/{key}.{fmt}", params={"month": month})
            assert got.status_code == 200, (key, fmt, got.text[:200])
    got = client.get("/api/exports/transactions.xlsx", params={"year": int(month[:4])})
    assert got.status_code == 200 and got.content[:2] == b"PK"
    assert client.get("/api/exports/debt_cost.csv").status_code == 200

    _alembic("downgrade", "0016")
    with get_engine().connect() as conn:
        gone = conn.execute(
            text("SELECT OBJECT_ID('[core].[monthly_report]', 'U')")
        ).scalar_one_or_none()
    assert gone is None
    _alembic("upgrade", "head")


def test_backup_and_restore_drill_on_sql_server(tmp_path: object) -> None:
    """F17: a real BACPAC export of the database with its manifest, then the restore drill into a
    scratch database on the same server, checked against the manifest (needs sqlpackage)."""
    import shutil
    from pathlib import Path

    from fastapi.testclient import TestClient
    from sqlalchemy.engine import make_url

    from app.config import get_settings
    from app.ingestion.storage import LocalStore, get_store
    from app.main import create_app
    from app.ops import backup
    from tests.fixtures.workbook import build

    if shutil.which("sqlpackage") is None:
        pytest.skip("sqlpackage is not installed")
    _alembic("downgrade", "0004")
    _alembic("upgrade", "head")
    app = create_app()
    app.dependency_overrides[get_store] = lambda: LocalStore(Path(str(tmp_path)) / "pdf")
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    TestClient(app).post(
        "/api/history/excel/load", files={"file": ("Cash Flow.xlsx", build(), xlsx)}
    )

    url = make_url(get_settings().database_url)
    server = f"{url.host},{url.port or 1433}"
    source = backup.Target(
        server, url.database or "", "sql", url.username, url.password, None, True
    )
    scratch = backup.Target(
        server, "cashflow_restore", "sql", url.username, url.password, None, True
    )
    store = backup.LocalBackupStore(Path(str(tmp_path)) / "backups")

    m = backup.export(source, store)
    assert m["size"] > 0 and m["tables"]["core.transaction"] > 0
    assert m["migration"] and m["transaction_total"] != "0.0000"
    r = backup.drill(scratch, store)
    assert r["ok"], r["problems"]
    assert r["rows"] == sum(m["tables"].values())
    # The scratch copy is a real database with the same rows.
    assert backup.facts(scratch)["tables"] == m["tables"]
    backup.drop_database(scratch)
