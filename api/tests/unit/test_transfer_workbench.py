"""ADR-075: settling transfers by hand."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Transaction

USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _add(
    db: Session, acc: Account, day: date, amount: str, desc: str, typ: str = "transfer"
) -> Transaction:
    n = db.query(Transaction).count()
    t = Transaction(
        natural_key=f"wb-{n}",
        account_id=acc.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=desc,
        type=typ,
        source="statement",
        status="confirmed",
    )
    db.add(t)
    db.flush()
    return t


def test_workbench_pair_and_outside(client: TestClient, db: Session) -> None:
    a, b = [x for x in db.scalars(select(Account)) if x.country == "EC"][:2]
    t1 = _add(db, a, date(2026, 8, 1), "2000.00", "TRANSFERENCIA CTAS TERCEROS BCA ENL")
    t2 = _add(db, a, date(2026, 8, 4), "2000.00", "TRANSFERENCIA CTAS TERCEROS BCA ENL")
    out = _add(db, b, date(2026, 8, 2), "-2000.00", "PAGO A TERCERO", typ="expense")
    db.commit()

    wb = client.get("/api/transfers/workbench").json()
    assert "Wise" in wb["places"]
    [bunch] = [x for x in wb["bunches"] if x["description"].startswith("TRANSFERENCIA CTAS")]
    assert [ln["transaction_id"] for ln in bunch["lines"]] == [t2.transaction_id, t1.transaction_id]
    first = next(ln for ln in bunch["lines"] if ln["transaction_id"] == t1.transaction_id)
    assert [c["transaction_id"] for c in first["candidates"]] == [out.transaction_id]

    r = client.post(
        "/api/transfers/pair", json={"a": t1.transaction_id, "b": out.transaction_id}, headers=USER
    )
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Transaction, out.transaction_id).type == "transfer"  # type: ignore[union-attr]
    assert (
        client.post(
            "/api/transfers/pair", json={"a": t1.transaction_id, "b": out.transaction_id}
        ).status_code
        == 409
    )

    r = client.post(
        "/api/transfers/outside",
        json={"ids": [t2.transaction_id], "place": "Lauren's flexible savings"},
        headers=USER,
    )
    assert r.json() == {"settled": 1}
    db.expire_all()
    t = db.get(Transaction, t2.transaction_id)
    assert t is not None and t.transfer_group_id == t.transaction_id
    assert t.notes == "Other side: Lauren's flexible savings"
    wb = client.get("/api/transfers/workbench").json()
    assert not [x for x in wb["bunches"] if x["description"].startswith("TRANSFERENCIA CTAS")]
