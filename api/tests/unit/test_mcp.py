"""F18: Claude's read-only MCP endpoint. The token, the protocol over HTTP, and each tool on a
small synthetic household (July to October)."""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import mcp_server
from app.config import get_settings
from app.db import reader
from app.main import create_app
from app.models import Account, Category, Transaction

TOKEN = "t" * 48
MCP_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture
def household(engine: Engine, db: Session, monkeypatch: pytest.MonkeyPatch) -> Engine:
    """A salary, groceries, dining that doubles in October, card interest in October."""
    monkeypatch.setattr(mcp_server, "get_reader_engine", lambda: engine)

    def acct(name: str) -> int:
        a = db.scalar(select(Account).where(Account.name == name))
        assert a is not None
        return a.account_id

    def cat(name: str) -> int:
        c = db.scalar(select(Category).where(Category.name == name))
        assert c is not None
        return c.category_id

    bank, card = acct("Produbanco Ahorros Hernan"), acct("Capital One Venture")
    n = 0

    def line(account: int, day: date, amount: str, category: int, kind: str, text: str) -> None:
        nonlocal n
        n += 1
        db.add(
            Transaction(
                natural_key=f"mcp-{n}",
                account_id=account,
                txn_date=day,
                cash_month=day.replace(day=1),
                amount=Decimal(amount),
                description_raw=text,
                merchant=text,
                type=kind,
                category_id=category,
                source="manual",
                status="confirmed",
            )
        )

    for month in (7, 8, 9, 10):
        line(bank, date(2026, month, 15), "3000", cat("Hernan"), "income", "PAYROLL")
        line(card, date(2026, month, 5), "-400", cat("Supermarket"), "expense", "SUPERMAXI 123")
        dining = "-300" if month == 10 else "-150"
        line(card, date(2026, month, 20), dining, cat("Restaurants & Cafés"), "expense", "BISTRO")
    line(card, date(2026, 10, 6), "-25", cat("Supermarket"), "expense", "SUPERMAXI 456")
    line(card, date(2026, 10, 25), "-42.10", cat("Credit Card Interest"), "fee_interest", "INT")
    db.commit()
    return engine


@pytest.fixture
def with_token(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MCP_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("MCP_TOKEN")
    get_settings.cache_clear()


def _rpc(client: TestClient, method: str, params: dict[str, Any] | None = None) -> Any:
    resp = client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------- the endpoint
def test_off_without_a_token(client: TestClient) -> None:
    resp = client.post("/mcp", json={})
    assert resp.status_code == 404 and resp.json()["detail"] == "The MCP endpoint is off."


def test_needs_the_token(with_token: None, client: TestClient) -> None:
    assert client.post("/mcp", json={}).status_code == 401
    wrong = client.post("/mcp", json={}, headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401 and wrong.headers["www-authenticate"] == "Bearer"


def test_the_protocol_over_http(
    with_token: None, household: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The signed-in people's allow-list doesn't apply to /mcp; the token does.
    monkeypatch.setenv("ALLOWED_EMAILS", "hernan@example.com")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        init = _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        info = init["result"]
        assert info["serverInfo"]["name"] == "household-cashflow"
        assert "dollarized" in info["instructions"]
        tools = {t["name"] for t in _rpc(client, "tools/list")["result"]["tools"]}
        assert tools == {
            "months",
            "cash_flow",
            "compare_months",
            "spending_by_category",
            "spending_lines",
            "top_merchants",
            "interest_and_fees",
            "balance_sheet",
            "loans",
            "monthly_report",
            "save_portfolio",
            "purchases",
        }
        called = _rpc(
            client,
            "tools/call",
            {"name": "compare_months", "arguments": {"month": "2026-10", "other": "2026-09"}},
        )["result"]
        assert not called.get("isError"), called
        got = called.get("structuredContent") or json.loads(called["content"][0]["text"])
        assert got["groups"][0]["group"] == "Dining" and got["groups"][0]["change"] == "150.00"
        # A people's page still needs a signed-in, allowed account.
        assert client.get("/api/reports").status_code == 403
    monkeypatch.delenv("ALLOWED_EMAILS")
    get_settings.cache_clear()


# ---------------------------------------------------------------- the tools
def test_months_and_cash_flow(household: Engine) -> None:
    assert mcp_server.months() == {"first": "2026-07", "last": "2026-10", "count": 4}
    flow = mcp_server.cash_flow("2026-09", "2026-10")
    assert [f["month"] for f in flow] == ["2026-09", "2026-10"]
    assert (flow[1]["income"], flow[1]["expenses"], flow[1]["net"]) == (
        "3000.00",
        "767.10",
        "2232.90",
    )
    assert flow[1]["savings_rate"] is not None and flow[1]["transactions"] == 5
    cash = mcp_server.cash_flow("2026-10", "2026-10", view="cash")
    assert "card_payments" in cash[0]
    with pytest.raises(ValueError, match="spending"):
        mcp_server.cash_flow("2026-10", "2026-10", view="other")
    with pytest.raises(ValueError, match="2026-10"):
        mcp_server.cash_flow("October", "2026-10")


def test_compare_months(household: Engine) -> None:
    got = mcp_server.compare_months("2026-10", "2026-09")
    assert got["spending_total"] == {"2026-10": "767.10", "2026-09": "550.00"}
    assert [g["group"] for g in got["groups"]] == ["Dining", "Financial Costs", "Groceries"]
    assert got["groups"][0] == {
        "group": "Dining",
        "2026-10": "300.00",
        "2026-09": "150.00",
        "change": "150.00",
    }
    assert got["cash_flow"]["2026-09"]["net"] == "2450.00"
    empty = mcp_server.compare_months("2026-10", "2020-01")
    assert empty["cash_flow"]["2020-01"] is None


def test_categories_lines_and_merchants(household: Engine) -> None:
    cats = mcp_server.spending_by_category("2026-10")
    groceries = next(c for c in cats if c["category"] == "Supermarket")
    assert (groceries["type"], groceries["amount"], groceries["transactions"]) == (
        "expense",
        "425.00",
        2,
    )
    assert any(c["type"] == "income" and c["amount"] == "3000.00" for c in cats)
    lines = mcp_server.spending_lines("2026-10", group="Groceries")
    assert [ln["amount"] for ln in lines] == ["400.00", "25.00"]
    assert lines[0]["account"] == "Capital One Venture"
    assert len(mcp_server.spending_lines("2026-10", merchant="maxi", limit=1)) == 1
    assert mcp_server.spending_lines("2026-10", category="Nope") == []
    top = mcp_server.top_merchants("2026-10")
    # Store numbers removed: both SUPERMAXI lines are one merchant.
    assert top[0]["merchant"].startswith("SUPERMAXI") and top[0]["amount"] == "425.00"
    assert top[0]["transactions"] == 2


def test_interest_and_fees(household: Engine) -> None:
    got = mcp_server.interest_and_fees(2026)
    assert (got["interest"], got["fees"]) == ("42.10", "0.00")
    assert got["lines"][0]["month"] == "2026-10" and got["lines"][0]["kind"] == "interest"
    assert mcp_server.interest_and_fees(2020)["lines"] == []


# ---------------------------------------------------------------- the read-only login
def test_reader_engine_and_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    reader.get_reader_engine.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "mssql+pyodbc://app:secret@db.example:1433/cashflow")
    monkeypatch.delenv("READER_PASSWORD", raising=False)
    get_settings.cache_clear()
    assert reader.ensure_reader().endswith("skipped (READER_PASSWORD not set)")
    monkeypatch.setenv("READER_PASSWORD", "r'eader")
    get_settings.cache_clear()
    url = reader.reader_url()
    assert url.username == "cashflow_reader" and url.password == "r'eader"
    assert url.host == "db.example" and url.database == "cashflow"
    assert reader._quoted("r'eader") == "r''eader"
    reader.get_reader_engine.cache_clear()
    get_settings.cache_clear()


# ---------------------------------------------------------------- balance sheet, loans, reports
def test_balance_sheet_loans_and_report(household: Engine, client: TestClient) -> None:
    from tests.fixtures import statements as s

    car = client.post(
        "/api/holdings",
        json={"name": "Car", "holding_class": "vehicle", "value": "15000", "as_of": "2026-01-01"},
    )
    assert car.status_code == 201
    loan = client.post(
        "/api/holdings",
        json={"name": "Mortgage", "holding_class": "loan", "value": "12000", "as_of": "2025-12-31"},
    ).json()["holding_id"]
    up = client.post(
        f"/api/holdings/{loan}/schedule",
        files={"file": ("t.pdf", s.loan_table(), "application/pdf")},
    )
    assert up.status_code == 200, up.text

    sheet = mcp_server.balance_sheet("2026-10-27")
    items = {i["name"]: i for i in sheet["items"]}
    assert items["Car"]["value"] == "15000.00" and items["Car"]["side"] == "asset"
    assert items["Mortgage"]["value"] == "2000.00" and items["Mortgage"]["source"] == "amortization"
    assert items["Mortgage"]["monthly_payment"] == "1022.50"
    assert sheet["net_worth"] == "13000.00" and len(sheet["net_worth_by_month"]) == 12

    [mortgage] = mcp_server.loans()
    assert (mortgage["paid"], mortgage["left"], mortgage["payoff"]) == (10, 2, "2026-12")
    assert mortgage["next_installments"][0] == {
        "month": "2026-11",
        "total": "1022.50",
        "principal": "1000.00",
        "interest": "20.00",
        "other": "2.50",
        "balance_after": "1000.00",
    }

    assert mcp_server.monthly_report("2026-10")["report"] is None
    made = client.post("/api/reports/2026-10/generate", params={"today": "2026-10-28"})
    assert made.status_code == 200, made.text
    saved = mcp_server.monthly_report("2026-10")
    assert saved["written_by"] == "rules" and 3 <= len(saved["findings"]) <= 5
    assert saved["facts"]["month"] == "2026-10"
