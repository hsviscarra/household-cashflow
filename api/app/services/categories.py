"""Deleting a category (ADR-034). A category nothing uses is simply removed. One that lines,
rules, bills or budgets use moves them to another category of the same kind first, with every
moved line written to the change log, so no amount disappears from the cash flow."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import (
    Budget,
    BudgetPlan,
    Category,
    ChangeLog,
    Counterparty,
    Holding,
    Invoice,
    MerchantRule,
    MerchantSuggestion,
    RecurringTemplate,
    StgTransaction,
    Transaction,
    TransferNote,
)


class CategoryError(Exception):
    """A category change that can't be done; `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Uses:
    """What still points at a category."""

    lines: int = 0
    rules: int = 0
    bills: int = 0
    budgets: int = 0
    other: int = 0  # people, balance-sheet items, transfer notes, statements waiting

    @property
    def total(self) -> int:
        """Everything that still points at the category."""
        return self.lines + self.rules + self.bills + self.budgets + self.other


_OTHER: Sequence[type] = (Counterparty, Holding, TransferNote, StgTransaction, Invoice)


def _count(db: Session, model: type, category_id: int) -> int:
    col = model.category_id  # type: ignore[attr-defined]
    return int(db.scalar(select(func.count()).select_from(model).where(col == category_id)) or 0)


def uses(db: Session, category_id: int) -> Uses:
    """What uses a category: lines, rules, bills, budgets and the rest. Nothing means it can go."""
    return Uses(
        lines=_count(db, Transaction, category_id),
        rules=_count(db, MerchantRule, category_id),
        bills=_count(db, RecurringTemplate, category_id),
        budgets=_count(db, Budget, category_id) + _count(db, BudgetPlan, category_id),
        other=sum(_count(db, m, category_id) for m in _OTHER),
    )


def _check_target(db: Session, c: Category, move_to: int) -> Category:
    target = db.get(Category, move_to)
    if target is None:
        raise CategoryError(f"Category {move_to} not found.", 404)
    if target.category_id == c.category_id:
        raise CategoryError("Choose another category to move its lines to.")
    if target.kind != c.kind:
        raise CategoryError(
            f"{target.name} counts as {target.kind} and {c.name} as {c.kind}: "
            "move them to a category of the same kind."
        )
    return target


def _move_budgets(db: Session, old: int, new: int) -> None:
    """Budgets are one per month, label and source: a clash adds the amounts together."""
    for b in list(db.scalars(select(Budget).where(Budget.category_id == old))):
        twin = db.scalars(
            select(Budget).where(
                Budget.category_id == new,
                Budget.month == b.month,
                Budget.label == b.label,
                Budget.source == b.source,
            )
        ).first()
        if twin is not None:
            twin.amount += b.amount
            db.delete(b)
        else:
            b.category_id = new
    for p in list(db.scalars(select(BudgetPlan).where(BudgetPlan.category_id == old))):
        clash = db.scalars(
            select(BudgetPlan).where(
                BudgetPlan.category_id == new, BudgetPlan.start_month == p.start_month
            )
        ).first()
        if clash is not None:
            db.delete(p)  # the target's own budget for that month wins
        else:
            p.category_id = new
    db.flush()


def delete(db: Session, c: Category, move_to: int | None, user: str) -> Uses:
    """Remove a category, moving whatever uses it to `move_to` first. Returns what moved."""
    children = _count_children(db, c.category_id)
    if children:
        raise CategoryError(
            f"{c.name} has {children} "
            f"{'subcategory' if children == 1 else 'subcategories'}: "
            "delete or move them to another group first.",
            409,
        )
    used = uses(db, c.category_id)
    if used.total and move_to is None:
        raise CategoryError(
            f"{c.name} is still used ({used.lines} lines, {used.rules} rules, {used.bills} "
            f"bills, {used.budgets} budgets): choose a category to move them to.",
            409,
        )
    if used.total and move_to is not None:
        target = _check_target(db, c, move_to)
        reason = f"Category {c.name} deleted; moved to {target.name}"[:200]
        ids = list(
            db.scalars(
                select(Transaction.transaction_id).where(Transaction.category_id == c.category_id)
            )
        )
        db.add_all(
            ChangeLog(
                table_name="core.transaction",
                row_id=tid,
                column_name="category_id",
                old_value=str(c.category_id),
                new_value=str(target.category_id),
                reason=reason,
                changed_by=user,
            )
            for tid in ids
        )
        for model in (Transaction, MerchantRule, RecurringTemplate, *_OTHER):
            col = model.category_id  # type: ignore[attr-defined]
            db.execute(
                update(model)
                .where(col == c.category_id)
                .values(category_id=target.category_id)
                .execution_options(synchronize_session=False)
            )
        _move_budgets(db, c.category_id, target.category_id)
    db.execute(
        MerchantSuggestion.__table__.delete().where(  # type: ignore[attr-defined]
            MerchantSuggestion.category_id == c.category_id
        )
    )
    db.delete(c)
    db.commit()
    return used


def _count_children(db: Session, category_id: int) -> int:
    q = select(func.count()).select_from(Category).where(Category.parent_id == category_id)
    return int(db.scalar(q) or 0)
