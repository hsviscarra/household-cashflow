"""ADR-073: money in, spent, set aside, free cash, left over; same days of the month before."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction


def _cat(db: Session, name: str) -> int:
    return db.scalars(select(Category.category_id).where(Category.name == name)).first()  # type: ignore[return-value]


def _add(
    db: Session, day: date, amount: str, typ: str, cat: str, month: date | None = None
) -> None:
    acc = db.scalars(select(Account)).first()
    assert acc is not None
    n = db.query(Transaction).count()
    db.add(
        Transaction(
            natural_key=f"m-{n}",
            account_id=acc.account_id,
            txn_date=day,
            cash_month=month or day.replace(day=1),
            amount=Decimal(amount),
            description_raw=cat,
            type=typ,
            category_id=_cat(db, cat),
            source="statement",
            status="confirmed",
        )
    )


def test_four_measures_and_same_days(client: TestClient, db: Session) -> None:
    # October, whole: salary, groceries, a refund, investing, the house.
    _add(db, date(2026, 10, 5), "100.00", "income", "Hernan")
    _add(db, date(2026, 10, 3), "-30.00", "expense", "Supermarket")
    _add(db, date(2026, 10, 20), "-50.00", "expense", "Supermarket")
    _add(db, date(2026, 10, 21), "10.00", "refund", "Supermarket")
    _add(db, date(2026, 10, 25), "-20.00", "savings", "Investing")
    _add(db, date(2026, 10, 23), "-40.00", "debt_payment", "New house")
    # A salary paid Nov 1 for October counts in October, but not in Oct 1-11.
    _add(db, date(2026, 11, 1), "500.00", "income", "Lauren", month=date(2026, 10, 1))
    # November so far.
    _add(db, date(2026, 11, 4), "-12.00", "expense", "Supermarket")
    db.commit()

    r = client.get(
        "/api/cashflow/measures", params={"month": "2026-11-01", "today": "2026-11-11"}
    ).json()
    assert r["running"] is True and r["through"] == "2026-11-11"
    assert Decimal(r["this"]["spent"]) == 12 and Decimal(r["this"]["money_in"]) == 0
    b = r["before"]
    assert (b["start"], b["end"]) == ("2026-10-01", "2026-10-11")
    assert Decimal(b["money_in"]) == 100 and Decimal(b["spent"]) == 30

    oct_ = client.get(
        "/api/cashflow/measures", params={"month": "2026-10-01", "today": "2026-11-11"}
    ).json()
    t = oct_["this"]
    assert oct_["running"] is False
    assert Decimal(t["money_in"]) == 600
    assert Decimal(t["spent"]) == 70  # 30 + 50 - 10
    assert Decimal(t["set_aside"]) == 60  # investing + the house
    assert Decimal(t["free_cash"]) == 530 and Decimal(t["left_over"]) == 470
    assert oct_["months"][-1]["month"] == "2026-10-01"
