"""ADR-055: money moved between countries through people. Synthetic data only."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Counterparty, Transaction
from app.services import transfers
from tests.unit.test_costs_api import _line


def _exchange(db: Session) -> Category:
    c = db.scalar(select(Category).where(Category.name == "Exchange through people"))
    assert c is not None and c.kind == "transfer"
    return c


def test_us_payment_and_ecuador_deposit_pair(db: Session) -> None:
    swap = _exchange(db)
    us = db.scalar(select(Account).where(Account.country == "US"))
    ec = db.scalar(select(Account).where(Account.country == "EC", Account.kind != "credit_card"))
    assert us is not None and ec is not None
    who = Counterparty(name="Exchanger", patterns="NAPOLES TRANSPORT", category_id=swap.category_id)
    db.add(who)
    db.flush()
    _line(
        db,
        us.account_id,
        date(2026, 9, 3),
        "-1500.00",
        "Zelle payment to Napoles Transport",
        swap.category_id,
        "transfer",
    )
    zelle = db.scalar(select(Transaction).where(Transaction.amount == -1500))
    assert zelle is not None
    zelle.counterparty_id = who.counterparty_id
    # The deposit in Ecuador says nothing about who, and comes a week later.
    _line(db, ec.account_id, date(2026, 9, 10), "1500.00", "TRANSFERENCIA RECIBIDA", None, "income")
    # Too late (12 days) and the wrong amount don't pair.
    _line(db, ec.account_id, date(2026, 9, 15), "1500.00", "TRANSFERENCIA OTRA", None, "income")
    for t in db.scalars(select(Transaction)):
        t.source = "statement"  # as if read from the statements
    db.commit()

    assert transfers.match(db).pairs == 1
    db.expire_all()
    legs = list(db.scalars(select(Transaction).where(Transaction.transfer_group_id.is_not(None))))
    assert {t.description_raw for t in legs} == {
        "Zelle payment to Napoles Transport",
        "TRANSFERENCIA RECIBIDA",
    }
    assert {(t.type, t.category_id) for t in legs} == {("transfer", swap.category_id)}
    # Within one country the window stays 5 days.
    assert transfers.ABROAD.days == 10 and transfers.WINDOW.days == 5
