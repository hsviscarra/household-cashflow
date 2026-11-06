"""ADR-028: merchants with visits and invoices, products with their price before and a cheaper
store, and ways to save."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Invoice, InvoiceLine, Transaction

n = 0


def _cat(db: Session, name: str) -> Category:
    c = db.scalar(select(Category).where(Category.name == name))
    assert c is not None
    return c


def _add(
    db: Session,
    day: date,
    amount: str,
    merchant: str,
    category: Category | None,
    typ: str = "expense",
    person: str = "Hernan",
) -> Transaction:
    global n
    n += 1
    account = db.scalar(select(Account).where(Account.kind == "checking"))
    assert account is not None
    t = Transaction(
        natural_key=f"s-{n}",
        account_id=account.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=f"{merchant} {n:06d}",
        merchant=merchant,
        type=typ,
        category_id=category.category_id if category else None,
        person=person,
        source="statement",
        status="confirmed",
    )
    db.add(t)
    db.flush()
    return t


def _invoice(
    db: Session,
    day: date,
    store: str,
    items: list[tuple[str, str, str]],
    paid: Transaction | None = None,
) -> None:
    global n
    n += 1
    total = sum(Decimal(t) for _, _, t in items)
    inv = Invoice(
        access_key=f"{n:049d}",
        issuer_ruc="1790016919001",
        issuer_name=store,
        number=f"001-001-{n:09d}",
        issue_date=day,
        subtotal=total,
        tax=Decimal(0),
        total=total,
        transaction_id=paid.transaction_id if paid else None,
        received_by="test",
    )
    db.add(inv)
    db.flush()
    for i, (desc, qty, line_total) in enumerate(items, 1):
        db.add(
            InvoiceLine(
                invoice_id=inv.invoice_id,
                line_no=i,
                description=desc,
                product_key=desc.upper(),
                quantity=Decimal(qty),
                unit_price=Decimal(line_total) / Decimal(qty),
                discount=Decimal(0),
                subtotal=Decimal(line_total),
                tax=Decimal(0),
                total=Decimal(line_total),
                product_group="Dairy & Eggs",
                group_source="rule",
            )
        )


def _get(client: TestClient, path: str, **params: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = client.get(f"/api/spending/{path}", params=params).json()
    return out


def test_merchants_products_and_ideas(client: TestClient, db: Session) -> None:
    market, fees = _cat(db, "Supermarket"), _cat(db, "Bank Fees")
    # Three months of groceries before, to set "usual" and "seen before".
    for month in (7, 8, 9):
        _add(db, date(2026, month, 5), "-200", "SUPERMAXI", market)
    _invoice(db, date(2026, 8, 5), "SUPERMAXI", [("Leche 1L", "2", "2.00")])
    _invoice(db, date(2026, 9, 5), "MEGAMAXI", [("Leche 1L", "2", "1.80"), ("Queso", "1", "5")])
    _invoice(db, date(2026, 6, 5), "AKI", [("Leche 1L", "4", "3.20")])

    a = _add(db, date(2026, 10, 3), "-310.55", "SUPERMAXI", market)
    _add(db, date(2026, 10, 9), "-140", "SUPERMAXI", market)
    _add(db, date(2026, 10, 10), "10", "SUPERMAXI", market, typ="refund")
    _invoice(
        db, date(2026, 10, 3), "SUPERMAXI", [("Leche 1L", "3", "3.30"), ("Queso", "1", "6")], a
    )
    for i in range(6):
        _add(db, date(2026, 10, 11 + i), "-4.50", "CAFE AROMA", market, person="Lauren")
    _add(db, date(2026, 10, 20), "-22.40", "RAPPI", market)
    _add(db, date(2026, 10, 21), "-18.10", "UBER EATS", market)
    _add(db, date(2026, 10, 22), "-80", "FERRETERIA KYWI", None)
    for i in range(3):
        _add(db, date(2026, 10, 25 + i), "-0.41", "TARIFA TRANSFERENCIA", fees, typ="fee_interest")
    db.commit()

    rows = _get(client, "merchants", month="2026-10-01")
    by = {r["merchant"]: r for r in rows}
    assert rows[0]["merchant"] == "SUPERMAXI"
    s = by["SUPERMAXI"]
    assert (Decimal(s["amount"]), s["visits"], s["invoices"]) == (Decimal("440.55"), 2, 1)
    assert Decimal(s["avg_ticket"]) == Decimal("220.28")
    assert by["CAFE AROMA"]["visits"] == 6
    lauren = _get(client, "merchants", month="2026-10-01", person="Lauren")
    assert [r["merchant"] for r in lauren] == ["CAFE AROMA"]
    only = _get(client, "merchants", month="2026-10-01", category_id=str(fees.category_id))
    assert [r["merchant"] for r in only] == ["TARIFA TRANSFERENCIA"]
    assert len(_get(client, "merchants", month="2026-10-01", group_id="0")) == 1

    prods = {p["description"]: p for p in _get(client, "products", month="2026-10-01")}
    milk = prods["Leche 1L"]
    assert Decimal(milk["unit_price"]) == Decimal("1.10")
    assert Decimal(milk["before"]) == Decimal("0.95")  # Aug and Sep: 3.80 for 4
    assert Decimal(milk["change"]) == Decimal("0.1579")
    assert (milk["cheaper_store"], Decimal(milk["cheaper_price"])) == ("AKI", Decimal("0.80"))
    assert Decimal(milk["could_save"]) == Decimal("0.90")
    assert prods["Queso"]["cheaper_store"] == "MEGAMAXI"  # 5.00 against 6.00
    assert Decimal(prods["Queso"]["could_save"]) == Decimal("1.00")
    assert _get(client, "products", month="2026-10-01", store="AKI") == []
    assert len(_get(client, "products", month="2026-10-01", product_group="Dairy & Eggs")) == 2
    assert _get(client, "products", month="2026-11-01") == []

    ideas = {i["key"]: i for i in _get(client, "ideas", month="2026-10-01")}
    assert ideas["fees"]["count"] == 3 and Decimal(ideas["fees"]["amount"]) == Decimal("1.23")
    assert ideas["delivery"]["count"] == 2 and Decimal(ideas["delivery"]["amount"]) == Decimal(
        "40.50"
    )
    assert ideas["small:CAFE AROMA"]["count"] == 6
    assert "new:FERRETERIA KYWI" in ideas
    assert "new:CAFE AROMA" not in ideas  # under $50
    assert Decimal(ideas["rising:" + str(market.parent_id)]["amount"]) > 0
    assert ideas["cheaper"]["count"] >= 1
    amounts = [Decimal(i["amount"]) for i in _get(client, "ideas", month="2026-10-01")]
    assert amounts == sorted(amounts, reverse=True)
    assert (
        _get(client, "ideas", month="2026-10-01", person="Lauren")[0]["key"] == "small:CAFE AROMA"
    )
