"""ADR-027: one month's flows by category with the month before, twelve months of totals, the
lines behind a band, and the person switch."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction

n = 0


def _cat(db: Session, name: str, parent: str | None = None) -> Category:
    q = select(Category).where(Category.name == name)
    if parent:
        p = db.scalar(select(Category).where(Category.name == parent, Category.parent_id.is_(None)))
        assert p is not None
        q = q.where(Category.parent_id == p.category_id)
    c = db.scalar(q)
    assert c is not None
    return c


def _add(
    db: Session,
    day: date,
    amount: str,
    typ: str,
    category: Category | None,
    person: str | None = "Hernan",
    source: str = "statement",
    merchant: str = "X",
    parent: int | None = None,
) -> Transaction:
    global n
    n += 1
    account = db.scalar(select(Account).where(Account.kind == "checking"))
    assert account is not None
    t = Transaction(
        natural_key=f"f-{n}",
        account_id=account.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=f"{merchant} {n}",
        merchant=merchant,
        type=typ,
        category_id=category.category_id if category else None,
        person=person,
        source=source,
        status="confirmed",
        parent_transaction_id=parent,
    )
    db.add(t)
    db.flush()
    return t


def _flows(client: TestClient, **params: str) -> dict[str, Any]:
    out: dict[str, Any] = client.get("/api/cashflow/flows", params=params).json()
    return out


def test_nothing_loaded(client: TestClient) -> None:
    out = _flows(client)
    assert out["source"] == "none" and out["flows"] == [] and out["months"] == []
    assert len(out["trend"]) == 12


def test_a_month_by_category_with_the_month_before(client: TestClient, db: Session) -> None:
    hernan, lauren = _cat(db, "Hernan", "Salary"), _cat(db, "Lauren", "Salary")
    market = _cat(db, "Supermarket")
    _add(db, date(2026, 9, 14), "5000", "income", hernan)
    _add(db, date(2026, 9, 20), "-300", "expense", market, merchant="SUPERMAXI")
    _add(db, date(2026, 10, 14), "5200", "income", hernan)
    _add(db, date(2026, 10, 14), "4000", "income", lauren, person="Lauren")
    _add(db, date(2026, 10, 3), "-120", "expense", market, merchant="SUPERMAXI")
    _add(db, date(2026, 10, 9), "-80", "expense", market, person="Lauren", merchant="MEGAMAXI")
    _add(db, date(2026, 10, 10), "-45", "expense", None, merchant="DEBITO")
    _add(db, date(2026, 10, 11), "-500", "transfer", None)  # not money in or out
    split = _add(db, date(2026, 10, 12), "-100", "expense", None, merchant="SPLIT")
    part = split.transaction_id
    _add(db, date(2026, 10, 12), "-100", "expense", market, merchant="SPLIT", parent=part)
    db.commit()

    out = _flows(client)
    assert (out["month"], out["prev_month"]) == ("2026-10-01", "2026-09-01")
    assert out["source"] == "statements"
    assert out["months"] == ["2026-10-01", "2026-09-01"]
    rows = {(f["type"], f["category_name"]): f for f in out["flows"]}
    assert Decimal(rows[("income", "Hernan")]["amount"]) == 5200
    assert Decimal(rows[("income", "Hernan")]["prev"]) == 5000
    assert Decimal(rows[("income", "Lauren")]["prev"]) == 0
    assert rows[("income", "Lauren")]["group_name"] == "Salary"
    groceries = rows[("expense", "Supermarket")]
    assert Decimal(groceries["amount"]) == Decimal(groceries["prev"]) == Decimal(300)
    assert groceries["transactions"] == 3
    assert rows[("expense", "Uncategorized")]["group_id"] == 0
    assert out["flows"][0]["category_name"] == "Hernan"  # biggest first
    trend = {m["month"]: m for m in out["trend"]}
    assert Decimal(trend["2026-10-01"]["money_in"]) == 9200
    assert Decimal(trend["2026-10-01"]["money_out"]) == 345
    assert Decimal(trend["2026-09-01"]["money_out"]) == 300

    # The switch: one person's lines.
    lauren_only = _flows(client, person="Lauren")
    assert {f["category_name"]: Decimal(f["amount"]) for f in lauren_only["flows"]} == {
        "Lauren": Decimal(4000),
        "Supermarket": Decimal(80),
    }
    assert _flows(client, month="2026-09-10")["month"] == "2026-09-01"

    def lines(**params: object) -> list[dict[str, Any]]:
        got: list[dict[str, Any]] = client.get(
            "/api/cashflow/lines", params={"month": "2026-10-01", **params}
        ).json()
        return got

    assert [ln["amount"] for ln in lines(side="in")] == ["5200.0000", "4000.0000"]
    assert len(lines(side="out")) == 4  # the transfer and the split parent left out
    assert len(lines(category_id=market.category_id)) == 3
    assert [ln["merchant"] for ln in lines(category_id=0)] == ["DEBITO"]
    assert [ln["merchant"] for ln in lines(group_id=0)] == ["DEBITO"]
    salary = rows[("income", "Lauren")]["group_id"]
    assert len(lines(group_id=salary)) == 2
    assert [ln["person"] for ln in lines(group_id=salary, person="Lauren")] == ["Lauren"]
    assert len(lines(merchant="SUPERMAXI", side="out")) == 1
    assert lines(category_id=market.category_id)[0]["account_name"]
    assert len(lines(person="Joint")) == 0
    # ADR-048: a type filter, and what the lines panel needs to fix a line.
    assert len(lines(type="income")) == 2 and lines(type="debt_payment") == []
    first_line = lines(category_id=market.category_id)[0]
    assert first_line["category_id"] == market.category_id
    assert first_line["merchant_key"] and first_line["cash_month"] == "2026-10-01"
    # Search finds any line around the month, counted or not (the transfer too).
    found = client.get("/api/cashflow/search", params={"q": "supermaxi", "month": "2026-10-01"})
    assert found.status_code == 200 and len(found.json()) >= 1
    assert (
        client.get("/api/cashflow/search", params={"q": "x", "month": "2026-10-01"}).status_code
        == 422
    )


def test_workbook_months_keep_the_workbook(client: TestClient, db: Session) -> None:
    market = _cat(db, "Supermarket")
    _add(db, date(2026, 5, 1), "-900", "expense", market, person=None, source="excel_history")
    _add(db, date(2026, 5, 3), "-50", "expense", market)  # a statement line in a workbook month
    db.commit()
    out = _flows(client)
    assert out["source"] == "excel"
    assert [Decimal(f["amount"]) for f in out["flows"]] == [Decimal(900)]
    assert len(_flows(client, person="Joint")["flows"]) == 1  # no person: joint
