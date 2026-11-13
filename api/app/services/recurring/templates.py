"""Recurring items and their months: create, change, stop, generate a month and copy it forward."""

from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    RecurringAmount,
    RecurringEntry,
    RecurringTemplate,
)
from app.services.recurring.base import (
    RecurringError,
    _log,
    active_in,
    add_months,
    amount_for,
    amounts,
    first,
    get_entry,
    get_template,
    months,
    signed,
)
from app.services.recurring.matching import _linked_entry_ids, _unlink_lines, match


def create_template(
    db: Session,
    *,
    name: str,
    category_id: int,
    type_: str,
    amount: Decimal,
    start_month: date,
    user: str,
    end_month: date | None = None,
    account_id: int | None = None,
    person: str | None = None,
    match_pattern: str | None = None,
    tolerance_pct: Decimal = Decimal(10),
    notes: str | None = None,
    sort_order: int | None = None,
    source: str = "manual",
    excel: tuple[str, str | None, str] | None = None,
    every_months: int = 1,
    due_day: int | None = None,
) -> RecurringTemplate:
    """Add a recurring item with its first amount; names are unique."""
    name = name.strip()
    if not name:
        raise RecurringError("Give the template a name.")
    if db.scalar(select(RecurringTemplate).where(RecurringTemplate.name == name)):
        raise RecurringError(f"A template named {name} already exists.", 409)
    if db.get(Category, category_id) is None:
        raise RecurringError("Choose a category.")
    if end_month is not None and first(end_month) < first(start_month):
        raise RecurringError("The last month is before the first month.")
    if sort_order is None:
        sort_order = (db.scalar(select(func.max(RecurringTemplate.sort_order))) or 0) + 1
    t = RecurringTemplate(
        name=name[:100],
        category_id=category_id,
        type=type_,
        account_id=account_id,
        person=person,
        match_pattern=(match_pattern or "").strip() or None,
        tolerance_pct=tolerance_pct,
        start_month=first(start_month),
        end_month=first(end_month) if end_month else None,
        is_active=True,
        sort_order=sort_order,
        source=source,
        excel_block=excel[0] if excel else None,
        excel_group=excel[1] if excel else None,
        excel_label=excel[2] if excel else None,
        notes=notes,
        every_months=every_months,
        due_day=due_day,
    )
    db.add(t)
    db.flush()
    db.add(
        RecurringAmount(
            template_id=t.template_id, from_month=t.start_month, amount=signed(type_, amount)
        )
    )
    _log(db, "core.recurring_template", t.template_id, "name", None, t.name, "Created", user)
    db.flush()
    return t


EDITABLE = (
    "name",
    "category_id",
    "type",
    "account_id",
    "person",
    "match_pattern",
    "tolerance_pct",
    "end_month",
    "is_active",
    "sort_order",
    "notes",
    "every_months",
    "due_day",
)


def _checked_changes(
    db: Session, t: RecurringTemplate, changes: dict[str, object]
) -> dict[str, object]:
    """A template's changes with the name, pattern and last month cleaned, or RecurringError."""
    changes = dict(changes)
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        clash = db.scalar(
            select(RecurringTemplate).where(
                RecurringTemplate.name == name, RecurringTemplate.template_id != t.template_id
            )
        )
        if not name or clash:
            raise RecurringError("Choose a name no other template has.", 409 if clash else 422)
        changes["name"] = name
    if "every_months" in changes and changes["every_months"] is None:
        del changes["every_months"]  # not nullable: leaving it out keeps it
    if "match_pattern" in changes:
        changes["match_pattern"] = str(changes["match_pattern"] or "").strip() or None
    if changes.get("end_month") is not None:
        end = first(changes["end_month"])  # type: ignore[arg-type]
        if end < t.start_month:
            raise RecurringError("The last month is before the first month.")
        changes["end_month"] = end
    return changes


def _flip_sign(db: Session, template_id: int, kind: str) -> None:
    """Income and expense flip the sign of every amount kept."""
    for a in amounts(db, [template_id])[template_id]:
        a.amount = signed(kind, a.amount)
    for e in db.scalars(select(RecurringEntry).where(RecurringEntry.template_id == template_id)):
        e.amount = signed(kind, e.amount)


def update_template(db: Session, template_id: int, changes: dict[str, object], user: str) -> None:
    """Change a recurring item's details, logging each change."""
    t = get_template(db, template_id)
    changes = _checked_changes(db, t, changes)
    if "type" in changes and changes["type"] != t.type:
        _flip_sign(db, template_id, str(changes["type"]))
    for key in EDITABLE:
        if key in changes:
            _log(
                db,
                "core.recurring_template",
                template_id,
                key,
                getattr(t, key),
                changes[key],
                "Edited",
                user,
            )
            setattr(t, key, changes[key])
    db.commit()


def stop(db: Session, template_id: int, month: date, user: str) -> int:
    """The item doesn't apply from `month` on (ADR-089): its last month becomes the one before
    (or, when it never ran, it is turned off), and the entries still planned from that month
    with no line paying them are removed. What was paid stays. Returns the entries removed."""
    month = first(month)
    t = get_template(db, template_id)
    last = add_months(month, -1)
    if last < t.start_month:
        update_template(db, template_id, {"is_active": False}, user)
    else:
        update_template(db, template_id, {"end_month": last}, user)
    linked = _linked_entry_ids(db)
    gone = [
        e.entry_id
        for e in db.scalars(
            select(RecurringEntry).where(
                RecurringEntry.template_id == template_id,
                RecurringEntry.month >= month,
                RecurringEntry.status == "planned",
            )
        )
        if e.entry_id not in linked
    ]
    for entry_id in gone:
        delete_entry(db, entry_id, user)
    return len(gone)


def delete_template(db: Session, template_id: int, user: str) -> None:
    """Remove a recurring item with its months; lines that paid them are unlinked, not deleted."""
    t = get_template(db, template_id)
    entry_ids = list(
        db.scalars(select(RecurringEntry.entry_id).where(RecurringEntry.template_id == template_id))
    )
    if entry_ids:
        _unlink_lines(db, entry_ids, user, "Template deleted")
    _log(db, "core.recurring_template", template_id, "name", t.name, None, "Deleted", user)
    db.execute(delete(RecurringEntry).where(RecurringEntry.template_id == template_id))
    db.execute(delete(RecurringAmount).where(RecurringAmount.template_id == template_id))
    db.delete(t)
    db.commit()


def change_amount(
    db: Session, template_id: int, from_month: date, amount: Decimal, user: str
) -> int:
    """From this month on the template's amount is this one: later changes are replaced, and every
    entry from that month that wasn't set by hand takes the new amount. Returns entries updated."""
    t = get_template(db, template_id)
    from_month = first(from_month)
    if from_month < t.start_month:
        raise RecurringError("That month is before the template starts.")
    value = signed(t.type, amount)
    db.execute(
        delete(RecurringAmount).where(
            RecurringAmount.template_id == template_id, RecurringAmount.from_month >= from_month
        )
    )
    db.add(RecurringAmount(template_id=template_id, from_month=from_month, amount=value))
    _log(
        db,
        "core.recurring_template",
        template_id,
        f"amount from {from_month:%Y-%m}",
        None,
        value,
        "Changed from this month on",
        user,
    )
    updated = 0
    touched = set()
    for e in db.scalars(
        select(RecurringEntry).where(
            RecurringEntry.template_id == template_id,
            RecurringEntry.month >= from_month,
            ~RecurringEntry.is_override,  # "= 0" on SQL Server (IS 0 is not valid T-SQL)
        )
    ):
        if e.amount != value:
            e.amount = value
            updated += 1
            touched.add(e.month)
    db.commit()
    for m in sorted(touched):
        match(db, m, user)
    return updated


# ---------------------------------------------------------------- month entries
def generate(db: Session, month: date, user: str) -> int:
    """One planned entry for every template active in the month that has none yet."""
    month = first(month)
    templates = [t for t in db.scalars(select(RecurringTemplate)) if active_in(t, month)]
    have = set(db.scalars(select(RecurringEntry.template_id).where(RecurringEntry.month == month)))
    history = amounts(db)
    created = 0
    for t in templates:
        if t.template_id in have:
            continue
        value = amount_for(history[t.template_id], month)
        if value is None:
            continue
        db.add(RecurringEntry(template_id=t.template_id, month=month, amount=value))
        created += 1
    db.commit()
    match(db, month, user)
    return created


MAX_COPY_MONTHS = 36  # months one copy may write to


def _copy_range(from_month: date, to_start: date, to_end: date) -> list[date]:
    """The months a copy writes to, or RecurringError when the range makes no sense."""
    if to_end < to_start:
        raise RecurringError("The range ends before it starts.")
    if to_start <= from_month <= to_end:
        raise RecurringError("Copy to other months than the one you copy from.")
    targets = months(to_start, to_end)
    if len(targets) > MAX_COPY_MONTHS:
        raise RecurringError(f"Copy to at most {MAX_COPY_MONTHS} months at a time.")
    return targets


def copy(
    db: Session,
    from_month: date,
    to_start: date,
    to_end: date,
    user: str,
    template_ids: list[int] | None = None,
) -> int:
    """Copy a month's expected amounts (and skips) to every month of a range. Copied amounts that
    differ from the template's are overrides. Entries with matched lines keep their amount.
    Returns the entries written."""
    from_month = first(from_month)
    targets = _copy_range(from_month, first(to_start), first(to_end))
    q = select(RecurringEntry).where(RecurringEntry.month == from_month)
    if template_ids:
        q = q.where(RecurringEntry.template_id.in_(template_ids))
    sources = list(db.scalars(q))
    if not sources:
        raise RecurringError(f"{from_month:%B %Y} has no entries to copy; generate it first.")
    history = amounts(db)
    linked = _linked_entry_ids(db)
    written = 0
    for m in targets:
        existing = {
            e.template_id: e
            for e in db.scalars(select(RecurringEntry).where(RecurringEntry.month == m))
        }
        for src in sources:
            target = existing.get(src.template_id)
            if target is not None and target.entry_id in linked:
                continue
            if target is None:
                target = RecurringEntry(template_id=src.template_id, month=m, amount=src.amount)
                db.add(target)
            target.amount = src.amount
            target.status = src.status
            target.is_override = src.amount != amount_for(history[src.template_id], m)
            written += 1
    db.commit()
    for m in targets:
        match(db, m, user)
    return written


def edit_entry(
    db: Session,
    entry_id: int,
    user: str,
    *,
    amount: Decimal | None = None,
    reset: bool = False,
    status: str | None = None,
    notes: str | None = None,
) -> RecurringEntry:
    """Change one month only: its amount (an override), back to the template's amount, skip it
    (this month doesn't happen; its lines are freed) or plan it again."""
    e = get_entry(db, entry_id)
    t = get_template(db, e.template_id)
    if amount is not None:
        value = signed(t.type, amount)
        _log(db, "core.recurring_entry", entry_id, "amount", e.amount, value, "This month", user)
        e.amount = value
        e.is_override = value != amount_for(amounts(db, [t.template_id])[t.template_id], e.month)
    if reset:
        default = amount_for(amounts(db, [t.template_id])[t.template_id], e.month)
        if default is not None:
            _log(db, "core.recurring_entry", entry_id, "amount", e.amount, default, "Reset", user)
            e.amount = default
        e.is_override = False
    if status is not None and status != e.status:
        _log(db, "core.recurring_entry", entry_id, "status", e.status, status, "This month", user)
        e.status = status
        if status == "skipped":
            _unlink_lines(db, [entry_id], user, "Month skipped")
    if notes is not None:
        e.notes = notes.strip()[:400] or None
    db.commit()
    if e.status == "planned":
        match(db, e.month, user)
    db.refresh(e)
    return e


def delete_entry(db: Session, entry_id: int, user: str) -> None:
    """Remove one month of a recurring item, unlinking the lines that paid it."""
    e = get_entry(db, entry_id)
    _unlink_lines(db, [entry_id], user, "Entry removed")
    _log(db, "core.recurring_entry", entry_id, "amount", e.amount, None, "Removed", user)
    db.delete(e)
    db.commit()
