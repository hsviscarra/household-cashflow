"""Seed v7: the fuller category tree, Hernan's edits kept, undone cleanly; money held for others
isn't a transfer missing its other side."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, MerchantRule, Transaction
from app.seeds import _category_ids, load_v7, unload_v7, v7
from app.services import transfers


def _ids(db: Session) -> dict[str, int]:
    return _category_ids(db.connection(), Category.__table__)


def test_the_tree(db: Session) -> None:
    ids = _ids(db)
    for path in (
        "Insurance/Health Insurance",
        "Insurance/Dad's Health Insurance",
        "Insurance/Car Insurance",
        "Entertainment & Leisure/Sports & Clubs",
        "Travel & Vacations/Lodging",
        "Transfers/Held for Others",
        "Other Income/Reimbursements from Others",
    ):
        assert path in ids, path
    assert "Travel" not in ids and "Health/Insurance" not in ids
    held = db.get(Category, ids["Transfers/Held for Others"])
    assert held is not None and held.kind == "transfer" and held.description
    car = db.get(Category, ids["Insurance/Car Insurance"])
    assert car is not None and car.kind == "expense" and car.is_fixed
    rules = {r.pattern: r.category_id for r in db.scalars(select(MerchantRule))}
    assert rules["FLEXJOBS"] == ids["Education & Career/Job Search"]
    assert rules["QUITO TENIS Y GOLF"] == ids["Entertainment & Leisure/Sports & Clubs"]


def test_loading_again_changes_nothing(db: Session) -> None:
    before = _ids(db)
    rules = len(list(db.scalars(select(MerchantRule))))
    load_v7(db.connection(), Category.__table__, MerchantRule.__table__)
    assert _ids(db) == before
    assert len(list(db.scalars(select(MerchantRule)))) == rules


def test_undo_and_redo_keep_the_moved_categories(db: Session) -> None:
    conn = db.connection()
    moved = _ids(db)["Insurance/Health Insurance"]
    unload_v7(conn, Category.__table__, MerchantRule.__table__)
    ids = _ids(db)
    assert ids["Health/Insurance"] == moved and "Travel" in ids
    assert "Insurance" not in ids
    assert not any(p.startswith(("Insurance/", "Travel &")) for p in ids)
    assert "Transfers/Held for Others" not in ids
    rules = {r.pattern: r.category_id for r in db.scalars(select(MerchantRule))}
    assert rules["FLEXJOBS"] == ids["Subscriptions & Software/Professional"]
    assert not {p for p, *_ in v7.MERCHANT_RULES} & set(rules)
    load_v7(conn, Category.__table__, MerchantRule.__table__)
    assert _ids(db)["Insurance/Health Insurance"] == moved


def test_hernans_edits_are_kept(db: Session) -> None:
    conn = db.connection()
    unload_v7(conn, Category.__table__, MerchantRule.__table__)
    ids = _ids(db)
    travel = db.get(Category, ids["Travel"])
    insurance = db.get(Category, ids["Health/Insurance"])
    assert travel is not None and insurance is not None
    travel.name = "Trips"  # renamed in Settings before the migration ran
    insurance.description = "Edited."
    db.add(MerchantRule(pattern="FITBOD", match_type="contains", category_id=ids["Health"]))
    db.flush()
    load_v7(conn, Category.__table__, MerchantRule.__table__)
    ids = _ids(db)
    assert "Trips" in ids and "Travel & Vacations" not in ids
    assert not any(p.startswith("Trips/") for p in ids)  # the subcategories need the group
    db.refresh(insurance)
    assert insurance.description == "Edited."
    fitbod = [r for r in db.scalars(select(MerchantRule)) if r.pattern == "FITBOD"]
    assert [r.category_id for r in fitbod] == [ids["Health"]]


def test_held_for_others_is_not_missing_its_other_side(db: Session) -> None:
    ids = _ids(db)
    bank = db.scalar(select(Account).where(Account.name == "BofA Adv Plus Banking"))
    assert bank is not None

    def line(key: str, amount: str, category: str | None) -> None:
        db.add(
            Transaction(
                natural_key=key,
                account_id=bank.account_id,
                txn_date=date(2026, 7, 10),
                cash_month=date(2026, 7, 1),
                amount=Decimal(amount),
                description_raw=key,
                type="transfer",
                category_id=ids[category] if category else None,
                source="statement",
                status="confirmed",
            )
        )

    line("for ruben", "12430", "Transfers/Held for Others")
    line("lent", "-200", "Transfers/Loans to Others")
    line("to savings", "-300", "Transfers/Between Own Accounts")
    line("card", "-150", "Transfers/Card Payment")
    line("no category", "-75", None)
    db.commit()
    got = sorted(t.description_raw for t in transfers.unmatched(db, date(2026, 7, 1)))
    assert got == ["card", "no category", "to savings"]
