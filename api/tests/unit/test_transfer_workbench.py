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


def test_a_wire_that_lost_a_fee_pairs_and_the_fee_counts(client: TestClient, db: Session) -> None:
    """ADR-080: 1,000 left the US account and 985 arrived in Ecuador: one click pairs them and
    the 15 becomes a bank fee."""
    us = next(x for x in db.scalars(select(Account)) if x.country == "US")
    ec = next(x for x in db.scalars(select(Account)) if x.country == "EC")
    sent = _add(db, us, date(2026, 8, 3), "-1000.00", "WIRE TYPE:INTL OUT")
    got = _add(db, ec, date(2026, 8, 6), "985.00", "TRANSFERENCIA DEL EXTERIOR")
    far = _add(db, ec, date(2026, 8, 6), "700.00", "TRANSFERENCIA DEL EXTERIOR")  # not a fee
    db.commit()

    wb = client.get("/api/transfers/workbench").json()
    line = next(
        ln
        for b in wb["bunches"]
        for ln in b["lines"]
        if ln["transaction_id"] == sent.transaction_id
    )
    [cand] = line["candidates"]
    assert cand["transaction_id"] == got.transaction_id and Decimal(cand["difference"]) == 15
    r = client.post(
        "/api/transfers/pair",
        json={"a": sent.transaction_id, "b": got.transaction_id},
        headers=USER,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    parts = list(
        db.scalars(
            select(Transaction).where(Transaction.parent_transaction_id == sent.transaction_id)
        )
    )
    by = {p.amount: p for p in parts}
    assert set(by) == {Decimal("-985.00"), Decimal("-15.00")}
    assert by[Decimal("-985.00")].type == "transfer"
    assert by[Decimal("-985.00")].transfer_group_id == got.transfer_group_id is not None
    assert by[Decimal("-15.00")].type in ("expense", "fee_interest")
    assert by[Decimal("-15.00")].transfer_group_id is None
    left = {
        ln["transaction_id"]
        for b in client.get("/api/transfers/workbench").json()["bunches"]
        for ln in b["lines"]
    }
    assert sent.transaction_id not in left and far.transaction_id in left


def test_the_same_transfer_is_settled_the_way_you_said(client: TestClient, db: Session) -> None:
    """ADR-080: say once where a transfer goes; the next one like it follows, after ten days."""
    from datetime import timedelta

    from app.services import transfers

    a = next(x for x in db.scalars(select(Account)) if x.country == "EC")
    today = date.today()
    first = _add(db, a, today - timedelta(days=60), "-300.00", "TRANSF AHORRO FLEX 0091")
    db.commit()
    r = client.post(
        "/api/transfers/outside",
        json={"ids": [first.transaction_id], "place": "Lauren's flexible savings"},
        headers=USER,
    )
    assert r.json()["settled"] == 1
    old = _add(db, a, today - timedelta(days=30), "-300.00", "TRANSF AHORRO FLEX 0091")
    fresh = _add(db, a, today - timedelta(days=2), "-300.00", "TRANSF AHORRO FLEX 0091")
    other = _add(db, a, today - timedelta(days=30), "-450.00", "TRANSF AHORRO FLEX 0091")
    db.commit()

    assert transfers.match(db, "hernan").settled == 1
    db.expire_all()
    assert old.transfer_group_id == old.transaction_id
    assert old.notes == "Other side: Lauren's flexible savings (as you said before)"
    assert fresh.transfer_group_id is None  # its other side may still arrive
    assert other.transfer_group_id is None  # another amount: not the same transfer
