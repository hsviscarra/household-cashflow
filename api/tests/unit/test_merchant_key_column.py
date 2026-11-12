"""ADR-086: the merchant key is stored on each line and kept in step by the flush hook."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.services import rules, rules_suggest


def _line(db: Session, n: int, text: str, category_id: int | None = None) -> Transaction:
    acct = db.scalars(select(Account)).first()
    assert acct is not None
    t = Transaction(
        natural_key=f"key-col-{n}",
        account_id=acct.account_id,
        txn_date=date(2026, 9, n),
        cash_month=date(2026, 9, 1),
        amount=Decimal("-10.00"),
        description_raw=text,
        type="expense",
        source="statement",
        category_id=category_id,
        category_source="manual" if category_id else None,
    )
    db.add(t)
    return t


def test_key_is_stored_and_follows_the_description(db: Session) -> None:
    t = _line(db, 1, "MICROSOFT*123456 MSBILL")
    db.commit()
    assert t.merchant_key == rules.key("MICROSOFT*123456 MSBILL") == "MICROSOFT MSBILL"
    t.description_raw = "SPOTIFY P1A2B3C4D5 STOCKHOLM"
    db.commit()
    assert t.merchant_key == "SPOTIFY STOCKHOLM"


def test_suggestions_group_in_the_database(db: Session) -> None:
    cats = [c for c in db.scalars(select(Category)) if c.parent_id][:2]
    # Twice the same way: suggested. Two ways: not. Once: not.
    _line(db, 1, "CAFE PRUEBA UNO 000111", cats[0].category_id)
    _line(db, 2, "CAFE PRUEBA UNO 000222", cats[0].category_id)
    _line(db, 3, "TIENDA PRUEBA DOS 000333", cats[0].category_id)
    _line(db, 4, "TIENDA PRUEBA DOS 000444", cats[1].category_id)
    _line(db, 5, "LIBRERIA PRUEBA TRES 000555", cats[0].category_id)
    _line(db, 6, "CAFE PRUEBA UNO 000666")  # no category yet: doesn't count
    db.commit()
    found = rules_suggest.suggestions(db)
    assert [(s.pattern, s.category_id, s.times) for s in found] == [
        ("CAFE PRUEBA UNO", cats[0].category_id, 2)
    ]
