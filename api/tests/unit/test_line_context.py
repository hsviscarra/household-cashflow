"""ADR-074: what's known about a line, and the card kept for Juliana's school."""

import json
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AppSetting, Category, Transaction
from tests.unit.test_shopping import _invoice

USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _cat(db: Session, name: str) -> int | None:
    return db.scalars(select(Category.category_id).where(Category.name == name)).first()


def _add(
    db: Session,
    acc: Account,
    day: date,
    amount: str,
    desc: str,
    typ: str = "expense",
    cat: str | None = None,
) -> Transaction:
    n = db.query(Transaction).count()
    t = Transaction(
        natural_key=f"lc-{n}",
        account_id=acc.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=desc,
        type=typ,
        category_id=_cat(db, cat) if cat else None,
        source="statement",
        status="confirmed",
    )
    db.add(t)
    db.flush()
    return t


def test_context_and_invoice_link(client: TestClient, db: Session) -> None:
    a, b = list(db.scalars(select(Account).limit(2)))
    old = _add(db, a, date(2026, 9, 22), "-89.69", "TRANSFERENCIA INTERNET", cat="Office Alícuota")
    line = _add(db, a, date(2026, 10, 22), "-89.69", "TRANSFERENCIA INTERNET")
    out = _add(db, a, date(2026, 10, 5), "-200.00", "TRANSFER TO SAVINGS", typ="transfer")
    side = _add(db, b, date(2026, 10, 6), "200.00", "TRANSFER FROM CHECKING", typ="transfer")
    shop = _add(db, a, date(2026, 10, 10), "-12.50", "SUPERMAXI")
    _invoice(db, date(2026, 10, 9), "CORPORACION FAVORITA C.A.", [("Leche", "1", "12.50")])
    db.commit()

    c = client.get(f"/api/transactions/{line.transaction_id}/context").json()
    assert [x["transaction_id"] for x in c["same_amount"]] == [old.transaction_id]
    assert c["same_amount"][0]["category_path"].endswith("Office Alícuota")

    t = client.get(f"/api/transactions/{out.transaction_id}/context").json()
    assert [x["transaction_id"] for x in t["transfer_candidates"]] == [side.transaction_id]

    s = client.get(f"/api/transactions/{shop.transaction_id}/context").json()
    [inv] = s["invoices"]
    assert inv["linked"] is False and inv["products"] == ["Leche"]
    r = client.put(
        f"/api/transactions/{shop.transaction_id}/invoice",
        json={"invoice_id": inv["invoice_id"]},
        headers=USER,
    )
    assert r.status_code == 200
    s = client.get(f"/api/transactions/{shop.transaction_id}/context").json()
    assert s["invoices"][0]["linked"] is True
    assert client.get("/api/transactions/999999/context").status_code == 404


def test_juliana_card_flags_what_isnt_school(client: TestClient, db: Session) -> None:
    acc = db.scalars(select(Account)).first()
    assert acc is not None
    db.add(
        AppSetting(
            setting_key=f"card-purpose:{acc.account_id}",
            updated_by="t",
            setting_value=json.dumps({"for": "Juliana", "usual": ["EINSTEIN", "SKOLE"]}),
        )
    )
    today = date.today()
    _add(db, acc, today, "-719.00", "COLEGIO EINSTEIN PENSI", cat="School")
    _add(db, acc, today, "-83.95", "SKOLE")
    _add(db, acc, today, "-1.20", "INTERES", typ="fee_interest")
    odd = _add(db, acc, today, "-45.00", "FARMACIAS FYBECA")
    db.commit()

    todo = client.get("/api/todo").json()
    [sec] = [x for x in todo["sections"] if x["key"] == "purpose"]
    assert sec["title"] == "Check: unusual on Juliana's card"
    assert [t["data"]["transaction_id"] for t in sec["tasks"]] == [odd.transaction_id]
    c = client.get(f"/api/transactions/{odd.transaction_id}/context").json()
    assert c["purpose"]["for_whom"] == "Juliana" and c["purpose"]["unusual"] is True
    # It belongs: not asked again.
    client.post("/api/todo/dismiss", json={"key": f"purpose:{odd.transaction_id}"}, headers=USER)
    todo = client.get("/api/todo").json()
    assert not [x for x in todo["sections"] if x["key"] == "purpose"]
