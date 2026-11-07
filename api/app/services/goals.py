"""Saving goals (ADR-040): how far each goal is, what it needs each month to arrive on its date,
and whether the planned monthly amount gets it there. The amount saved is the linked bank
account's or balance-sheet item's latest value (a purchase in progress counts what's paid), or
the amount typed by hand when nothing is linked."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Goal
from app.services import networth
from app.services.recurring import first

ZERO = Decimal(0)
CENT = Decimal("0.01")


class GoalError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Place:
    key: str
    name: str
    value: Decimal | None
    as_of: date | None


def places(db: Session, today: date) -> dict[str, Place]:
    """Where a goal's money can be kept: bank accounts and asset items (purchases count what's
    paid)."""
    out = {}
    for i in networth.accounts(db, today) + networth.holdings(db, today):
        if i.side != "asset" or not i.is_active:
            continue
        value = i.purchase.paid if i.purchase is not None else i.value
        out[i.key] = Place(i.key, i.name, value, i.as_of)
    return out


def months_between(today: date, target: date) -> int:
    """Whole months from this month to the target's month, counting the target's month: from
    November to December is 2 (November and December can still be funded)."""
    return (target.year - today.year) * 12 + target.month - today.month + 1


@dataclass
class GoalView:
    goal_id: int
    name: str
    target_amount: Decimal
    target_date: date | None
    item_key: str | None
    place_name: str | None
    saved_amount: Decimal | None
    monthly_amount: Decimal | None
    is_active: bool
    notes: str | None
    current: Decimal
    as_of: date | None
    share: Decimal  # 0..1
    left: Decimal
    months_left: int | None
    needed_monthly: Decimal | None  # to arrive on the date
    projected: Decimal | None  # at the date, with the planned monthly amount
    status: str  # reached, on_pace, behind, late, open (no date)


def view(g: Goal, where: dict[str, Place], today: date) -> GoalView:
    place = where.get(g.item_key) if g.item_key else None
    if place is not None:
        current, as_of = place.value or ZERO, place.as_of
    else:
        current, as_of = g.saved_amount or ZERO, None
    left = max(ZERO, g.target_amount - current)
    share = min(Decimal(1), current / g.target_amount) if g.target_amount else ZERO
    months = needed = projected = None
    if left == 0:
        status = "reached"
    elif g.target_date is None:
        status = "open"
    else:
        months = months_between(first(today), g.target_date)
        if months <= 0:
            status = "late"
        else:
            needed = (left / months).quantize(CENT, ROUND_CEILING)
            projected = current + (g.monthly_amount or ZERO) * months
            status = "on_pace" if projected >= g.target_amount else "behind"
    return GoalView(
        g.goal_id,
        g.name,
        g.target_amount,
        g.target_date,
        g.item_key,
        place.name if place else None,
        g.saved_amount,
        g.monthly_amount,
        g.is_active,
        g.notes,
        current,
        as_of,
        share.quantize(Decimal("0.0001")),
        left,
        months,
        needed,
        projected,
        status,
    )


def all_goals(db: Session, today: date | None = None) -> list[GoalView]:
    today = today or date.today()
    where = places(db, today)
    goals = db.scalars(select(Goal).order_by(Goal.is_active.desc(), Goal.sort_order, Goal.goal_id))
    return [view(g, where, today) for g in goals]


FIELDS = {
    "name",
    "target_amount",
    "target_date",
    "item_key",
    "saved_amount",
    "monthly_amount",
    "is_active",
    "notes",
}


def _check(db: Session, values: dict[str, object], today: date) -> None:
    key = values.get("item_key")
    if key and key not in places(db, today):
        raise GoalError(f"{key} isn't a bank account or asset on Net worth.")


def create(db: Session, values: dict[str, object], user: str, today: date | None = None) -> Goal:
    _check(db, values, today or date.today())
    g = Goal(**{k: v for k, v in values.items() if k in FIELDS}, created_by=user[:320])
    db.add(g)
    db.commit()
    return g


def update(
    db: Session, goal_id: int, changes: dict[str, object], today: date | None = None
) -> Goal:
    g = db.get(Goal, goal_id)
    if g is None:
        raise GoalError(f"Goal {goal_id} not found.", 404)
    _check(db, changes, today or date.today())
    for k, v in changes.items():
        if k in FIELDS:
            setattr(g, k, v)
    if g.target_amount is None or g.target_amount <= 0:
        raise GoalError("The target must be more than 0.")
    db.commit()
    return g


def delete(db: Session, goal_id: int) -> None:
    g = db.get(Goal, goal_id)
    if g is None:
        raise GoalError(f"Goal {goal_id} not found.", 404)
    db.delete(g)
    db.commit()
