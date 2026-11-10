"""The invoice decides the category (ADR-066).

When an electronic invoice is matched to the card or bank line that paid it, its products say
what was bought better than the merchant's name: a Supermaxi receipt that is mostly food is
groceries, one that is mostly medicine is pharmacy, a hardware store's is home maintenance.

Each product's category is the one a person chose for it (ADR-050), else the one its aisle maps
to. When one category holds at least SHARE of the invoice, the paying line gets it, unless a
person chose the line's category, it is split, or it is a transfer. Every change is logged.
"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased, selectinload

from app.models import Category, ChangeLog, Invoice, Transaction

SHARE = Decimal("0.6")
ZERO = Decimal(0)
# Aisle (product group) → "Group/Category" of the app.
AISLE = {
    "Meat & Fish": "Groceries/Supermarket",
    "Dairy & Eggs": "Groceries/Supermarket",
    "Fruit & Vegetables": "Groceries/Supermarket",
    "Bakery": "Groceries/Supermarket",
    "Pantry": "Groceries/Supermarket",
    "Snacks & Sweets": "Groceries/Supermarket",
    "Drinks": "Groceries/Supermarket",
    "Alcohol": "Groceries/Supermarket",
    "Frozen & Ready Meals": "Groceries/Supermarket",
    "Household & Cleaning": "Groceries/Supermarket",
    "Personal Care": "Groceries/Supermarket",
    "Baby": "Childcare/Baby & Kids Stores",
    "Health & Pharmacy": "Health/Pharmacy",
    "Pets": "Pets/Pet Food & Supplies",
    "Car": "Transport/Fuel",
}
# A person's choice, a split or a transfer is never overridden.
KEEP = ("manual", "split", "match", "person", "note")


def _paths(db: Session) -> dict[str, int]:
    parent = aliased(Category)
    rows = db.execute(
        select(parent.name, Category.name, Category.category_id).join(
            parent, parent.category_id == Category.parent_id
        )
    )
    return {f"{g}/{c}": cid for g, c, cid in rows}


def decide(inv: Invoice, paths: dict[str, int]) -> int | None:
    """The category holding at least SHARE of the invoice, or None."""
    total = sum((ln.total for ln in inv.lines), ZERO)
    if total <= 0:
        return None
    by: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for ln in inv.lines:
        cid = ln.category_id or paths.get(AISLE.get(ln.product_group or "", ""))
        if cid is not None:
            by[cid] += ln.total
    if not by:
        return None
    cid, amount = max(by.items(), key=lambda kv: kv[1])
    return cid if amount >= total * SHARE else None


def apply(db: Session, user: str = "system", since: object = None) -> int:
    """Give each matched line its invoice's category. Returns how many lines changed."""
    paths = _paths(db)
    q = (
        select(Invoice)
        .options(selectinload(Invoice.lines))
        .where(Invoice.transaction_id.is_not(None))
    )
    if since is not None:
        q = q.where(Invoice.issue_date >= since)
    invoices = list(db.scalars(q))
    lines = (
        {
            t.transaction_id: t
            for t in db.scalars(
                select(Transaction).where(
                    Transaction.transaction_id.in_([i.transaction_id for i in invoices])
                )
            )
        }
        if invoices
        else {}
    )
    changed = 0
    for inv in invoices:
        t = lines.get(inv.transaction_id or 0)
        if (
            t is None
            or t.category_source in KEEP
            or t.type == "transfer"
            or t.transfer_group_id is not None
        ):
            continue
        cid = decide(inv, paths)
        if cid is None or cid == t.category_id:
            continue
        db.add(
            ChangeLog(
                table_name="core.transaction",
                row_id=t.transaction_id,
                column_name="category_id",
                old_value=None if t.category_id is None else str(t.category_id),
                new_value=str(cid),
                reason=f"Invoice products ({inv.issuer_name})"[:200],
                changed_by=user[:320],
            )
        )
        t.category_id, t.category_source = cid, "invoice"
        changed += 1
    if changed:
        db.commit()
    return changed
