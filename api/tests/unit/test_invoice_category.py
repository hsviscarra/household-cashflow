"""ADR-066: the invoice's products decide the category of the line that paid it."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeLog, InvoiceLine, Transaction
from app.services import invoice_category
from tests.unit.test_shopping import _add, _cat, _invoice


def test_products_decide_and_a_persons_choice_stays(db: Session) -> None:
    other = _cat(db, "Other Retail")
    market = _cat(db, "Supermarket")
    pharmacy = _cat(db, "Pharmacy")
    food = _add(db, date(2026, 10, 4), "-10.00", "SUPERMAXI", other)
    meds = _add(db, date(2026, 10, 5), "-20.00", "SUPERMAXI", None)
    mine = _add(db, date(2026, 10, 6), "-5.00", "SUPERMAXI", other)
    mine.category_source = "manual"
    mixed = _add(db, date(2026, 10, 7), "-10.00", "SUPERMAXI", None)
    _invoice(db, date(2026, 10, 4), "SUPERMAXI", [("LECHE", "1", "8.00"), ("X", "1", "2.00")], food)
    _invoice(db, date(2026, 10, 5), "SUPERMAXI", [("PARACETAMOL", "1", "20.00")], meds)
    _invoice(db, date(2026, 10, 6), "SUPERMAXI", [("LECHE", "1", "5.00")], mine)
    _invoice(db, date(2026, 10, 7), "SUPERMAXI", [("A", "1", "5.00"), ("B", "1", "5.00")], mixed)
    db.flush()
    for ln in db.scalars(select(InvoiceLine)):
        if ln.description == "PARACETAMOL":
            ln.product_group = "Health & Pharmacy"
        elif ln.description == "X":
            ln.product_group = None
        elif ln.description == "B":
            ln.product_group = "Services"  # maps to nothing: 50% isn't enough
    db.commit()

    assert invoice_category.apply(db) == 2
    db.expire_all()
    got = {t.transaction_id: t for t in db.scalars(select(Transaction))}
    assert got[food.transaction_id].category_id == market.category_id
    assert got[food.transaction_id].category_source == "invoice"
    assert got[meds.transaction_id].category_id == pharmacy.category_id
    assert got[mine.transaction_id].category_id == other.category_id  # a person chose it
    assert got[mixed.transaction_id].category_id is None
    logged = db.scalar(select(ChangeLog).where(ChangeLog.row_id == food.transaction_id))
    assert logged is not None and logged.reason.startswith("Invoice products")
    assert invoice_category.apply(db) == 0  # nothing left to change
