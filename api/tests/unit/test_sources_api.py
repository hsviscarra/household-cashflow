"""F19 (ADR-018): statements count from a chosen month; the workbook stays as a reference that
the check compares them with. Moving the month changes which source counts, never the data."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.services import recurring, sources
from tests.fixtures.workbook import build

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
JAN = "2026-01-01"


def _monthly(client: TestClient, view: str = "spending") -> dict[str, dict[str, Any]]:
    rows = client.get("/api/cashflow/monthly", params={"view": view}).json()
    return {m["cash_month"]: m for m in rows}


def _statement_lines(db: Session) -> None:
    """January 2026 as the statements tell it: Lauren's salary, a doctor, groceries."""
    bank = db.scalar(select(Account).where(Account.name == "Produbanco Ahorros Hernan"))
    assert bank is not None

    def cat(name: str) -> int:
        c = db.scalar(select(Category).where(Category.name == name))
        assert c is not None, name
        return c.category_id

    for n, (day, amount, category, kind) in enumerate(
        [
            (5, "3100", "Lauren", "income"),
            (9, "-60.10", "Doctors", "expense"),
            (12, "-250", "Supermarket", "expense"),
        ],
        start=1,
    ):
        db.add(
            Transaction(
                natural_key=f"src-{n}",
                account_id=bank.account_id,
                txn_date=date(2026, 1, day),
                cash_month=date(2026, 1, 1),
                amount=Decimal(amount),
                description_raw=f"LINE {n}",
                type=kind,
                category_id=cat(category),
                source="statement",
                status="confirmed",
            )
        )
    db.commit()


def test_statements_from_a_month(client: TestClient, db: Session) -> None:
    files = {"file": ("Cash Flow.xlsx", build(), XLSX)}
    assert client.post("/api/history/excel/load", files=files, headers=USER).status_code == 200
    _statement_lines(db)

    # Not set: the workbook wins January (ADR-004); the statements wait.
    out = client.get("/api/sources").json()
    assert out["statements_from"] is None and out["check"] == []
    assert (out["workbook_first"], out["workbook_last"]) == ("2019-11-01", JAN)
    assert Decimal(_monthly(client)[JAN]["income"]) == Decimal("8500.25")
    assert date(2026, 1, 1) in recurring.excel_months(db)

    # From January 2026 statements count; the workbook's January rows are a reference only.
    resp = client.put("/api/sources", json={"statements_from": "2026-01-15"}, headers=USER)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["statements_from"] == JAN
    jan = _monthly(client)[JAN]
    assert (Decimal(jan["income"]), Decimal(jan["expenses"])) == (Decimal(3100), Decimal("310.1"))
    assert Decimal(_monthly(client, "cash")[JAN]["income"]) == Decimal(3100)
    assert Decimal(_monthly(client)["2019-12-01"]["net"]) == Decimal(280)  # earlier: workbook
    assert date(2026, 1, 1) not in recurring.excel_months(db)
    spending = client.get("/api/spending", params={"month": JAN}).json()
    assert spending["source"] == "statements"

    # The check: January's workbook and statement totals, biggest gap first.
    [check] = out["check"]
    assert check["month"] == JAN and check["statement_lines"] == 3
    assert Decimal(check["workbook_income"]) == Decimal("8500.25")
    assert Decimal(check["statements_income"]) == Decimal(3100)
    assert Decimal(check["workbook_spending"]) == Decimal("135.45")
    assert Decimal(check["statements_spending"]) == Decimal("310.10")
    groceries = check["groups"][0]
    assert groceries["group"] == "Groceries" and Decimal(groceries["difference"]) == 250
    health = next(g for g in check["groups"] if g["group"] == "Health")
    assert Decimal(health["difference"]) == 0  # the doctor is in both

    # Back to the workbook: nothing was deleted.
    out = client.put("/api/sources", json={"statements_from": None}, headers=USER).json()
    assert out["statements_from"] is None
    assert Decimal(_monthly(client)[JAN]["income"]) == Decimal("8500.25")


def test_refusals_and_status(client: TestClient, db: Session) -> None:
    resp = client.put("/api/sources", json={"statements_from": "2999-01-01"}, headers=USER)
    assert resp.status_code == 422 and "hasn't started" in resp.json()["detail"]
    # With no workbook loaded the setting still saves, and the check is empty.
    out = client.put("/api/sources", json={"statements_from": "2026-01-01"}).json()
    assert out["statements_from"] == JAN and out["check"] == []
    assert sources.statements_from(db) == date(2026, 1, 1)
    # Changing it again updates the one setting.
    client.put("/api/sources", json={"statements_from": "2026-06-01"})
    assert sources.statements_from(db) == date(2026, 6, 1)
    # Data Status: months from the setting are statement months, to be completed.
    files = {"file": ("Cash Flow.xlsx", build(), XLSX)}
    client.post("/api/history/excel/load", files=files, headers=USER)
    client.put("/api/sources", json={"statements_from": "2026-01-01"})
    status = client.get("/api/status", params={"today": "2026-03-10"}).json()
    assert status["excel_through"] == "2025-01-01"
    statement_months = [m["month"] for m in status["months"] if m["source"] == "statements"]
    assert JAN in statement_months and statement_months[-1] == "2025-02-01"
