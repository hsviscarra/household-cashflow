"""ADR-084: a salary counts in the month it pays for; everything else in the month of its date."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Transaction
from app.services.payday import month_for
from tests.unit.test_line_context import USER, _add, _cat


def test_month_for() -> None:
    assert month_for(date(2026, 10, 20), True) == date(2026, 11, 1)  # Hernan, the 20th
    assert month_for(date(2026, 10, 31), True) == date(2026, 11, 1)  # Lauren, the last day
    assert month_for(date(2026, 11, 1), True) == date(2026, 11, 1)  # her payroll slipped a day
    assert month_for(date(2026, 12, 20), True) == date(2027, 1, 1)
    assert month_for(date(2026, 10, 15), True) == date(2026, 11, 1)
    assert month_for(date(2026, 10, 14), True) == date(2026, 10, 1)
    assert month_for(date(2026, 10, 20), False) == date(2026, 10, 1)


def test_a_line_moves_when_it_becomes_a_salary(client: TestClient, db: Session) -> None:
    a = db.scalars(select(Account).limit(1)).one()
    pay = _add(db, a, date(2026, 10, 20), "4998.87", "PAYROLL ACME")
    rent = _add(db, a, date(2026, 10, 20), "575.00", "ARRIENDO OFICINA", cat="Office Rent")
    spent = _add(db, a, date(2026, 10, 20), "-80.00", "SUPERMAXI", cat="Supermarket")
    db.commit()
    # No category yet: the month of its date. Other income and spending never move.
    assert pay.cash_month == rent.cash_month == spent.cash_month == date(2026, 10, 1)

    salary = db.scalars(
        select(Transaction.category_id).where(Transaction.category_id == _cat(db, "Hernan"))
    ).first() or _cat(db, "Hernan")
    r = client.patch(
        f"/api/transactions/{pay.transaction_id}", json={"category_id": salary}, headers=USER
    )
    assert r.status_code == 200 and r.json()["cash_month"] == "2026-11-01"
    assert r.json()["txn_date"] == "2026-10-20"  # the date itself never changes

    back = client.patch(
        f"/api/transactions/{pay.transaction_id}",
        json={"category_id": _cat(db, "Office Rent")},
        headers=USER,
    )
    assert back.json()["cash_month"] == "2026-10-01"
