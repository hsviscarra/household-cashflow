"""ADR-089: a person says which month a line counts in; a bill is stopped where it's listed."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, ChangeLog, RecurringEntry, Transaction
from app.services import recurring, todo

USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def _line(db: Session, n: int, day: date, amount: str, text: str, category: str) -> Transaction:
    cat = db.scalar(select(Category).where(Category.name == category))
    acct = db.scalars(select(Account)).first()
    assert cat is not None and acct is not None
    t = Transaction(
        natural_key=f"override-{n}",
        account_id=acct.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=Decimal(amount),
        description_raw=text,
        type="income" if Decimal(amount) > 0 else "expense",
        category_id=cat.category_id,
        source="statement",
    )
    db.add(t)
    return t


def test_a_bonus_counts_in_its_own_month(client: TestClient, db: Session) -> None:
    # A salary on the 23rd counts in November by the rule (ADR-084); this one is October's bonus.
    bonus = _line(db, 1, date(2026, 10, 23), "2500", "TRANSFERENCIA BONO ANUAL", "Hernan")
    db.commit()
    assert bonus.cash_month == date(2026, 11, 1)
    url = f"/api/transactions/{bonus.transaction_id}"
    out = client.patch(url, json={"counts_in": "2026-10-15"}, headers=USER).json()
    assert out["cash_month"] == "2026-10-01" and out["month_override"] == "2026-10-01"
    log = db.scalars(select(ChangeLog).where(ChangeLog.column_name == "month_override")).one()
    assert (log.old_value, log.new_value) == (None, "2026-10-01")
    assert log.changed_by == "hernan@example.com"
    # Another change to the line keeps the chosen month.
    client.patch(url, json={"notes": "Yearly bonus"}, headers=USER)
    db.refresh(bonus)
    assert bonus.cash_month == date(2026, 10, 1)
    # Too far is a mistake, and null hands the line back to the rule.
    far = client.patch(url, json={"counts_in": "2026-07-01"}, headers=USER)
    assert far.status_code == 422 and "October" in far.json()["detail"]
    back = client.patch(url, json={"counts_in": None}, headers=USER).json()
    assert back["cash_month"] == "2026-11-01" and back["month_override"] is None


def test_stop_a_bill_from_a_month(client: TestClient, db: Session) -> None:
    water = db.scalar(select(Category).where(Category.name == "Water"))
    assert water is not None
    made = client.post(
        "/api/recurring/templates",
        json={
            "name": "Gym",
            "category_id": water.category_id,
            "type": "expense",
            "amount": "30",
            "start_month": "2026-09-01",
            "due_day": 5,
        },
    ).json()
    for month in ("2026-09-01", "2026-10-01", "2026-11-01"):
        client.post("/api/recurring/generate", json={"month": month})
    bills = client.get(
        "/api/recurring/bills", params={"month": "2026-11-01", "today": "2026-11-12"}
    ).json()["bills"]
    gym = next(b for b in bills if b["name"] == "Gym")
    assert gym["status"] == "late" and gym["entry_id"] is not None

    url = f"/api/recurring/templates/{made['template_id']}/stop"
    out = client.post(url, json={"month": "2026-11-01"}, headers=USER)
    assert out.status_code == 200 and out.json() == {"count": 1}
    assert recurring.get_template(db, made["template_id"]).end_month == date(2026, 10, 1)
    left = db.scalars(
        select(RecurringEntry.month).where(RecurringEntry.template_id == made["template_id"])
    )
    assert sorted(left) == [date(2026, 9, 1), date(2026, 10, 1)]
    after = client.get(
        "/api/recurring/bills", params={"month": "2026-11-01", "today": "2026-11-12"}
    ).json()["bills"]
    assert not [b for b in after if b["name"] == "Gym"]
    # Stopped from its first month: it never ran, so it is turned off.
    client.post(url, json={"month": "2026-09-01"}, headers=USER)
    db.expire_all()
    assert recurring.get_template(db, made["template_id"]).is_active is False


def test_to_do_lists_the_most_money_first(db: Session) -> None:
    for n, (amount, text) in enumerate(
        [
            ("-12.00", "TIENDA UNO 000111"),
            ("-950.00", "TIENDA DOS 000222"),
            ("-80.00", "TIENDA TRES"),
        ]
    ):
        t = _line(db, 10 + n, date(2026, 11, 3), amount, text, "Water")
        t.category_id = None
    db.commit()
    section = next(s for s in todo.build(db, date(2026, 11, 12)).sections if s.key == "categorize")
    assert [t.amount for t in section.tasks] == [
        Decimal("-950.00"),
        Decimal("-80.00"),
        Decimal("-12.00"),
    ]
