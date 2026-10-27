"""Recurring entries (F11, ADR-008).

A template is a row that repeats every month (salary, rent, condo fee, the card payment). Its
amount is kept from a month on (core.recurring_amount), so "change from month X" is one row. Each
month gets one entry per active template with the expected amount; a cell edited by hand (or
copied) is an override and template changes leave it alone.

Matching links the month's lines to the entries they pay (transaction.recurring_entry_id):
- months covered by the Excel history link only Excel lines, and a template made from a workbook
  row links that row's cell exactly, whatever its amount;
- other months link statement and manual lines of the template's category (or still without a
  category when the template has a pattern), on its account (the line's or its matched transfer's
  other side) and containing its pattern when those are set, within the tolerance (a percentage of
  the expected amount, at least 1.00);
- one line close enough wins; otherwise several lines that only this entry can take are linked
  together when their sum is within tolerance (a salary paid in two halves).
A matched entry is never re-matched; unlinking or skipping frees its lines.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    Category,
    ChangeLog,
    ExcelCell,
    RecurringAmount,
    RecurringEntry,
    RecurringTemplate,
    Transaction,
)
from app.services.excel_mapping import lookup, norm

MIN_TOLERANCE = Decimal("1.00")
EXCEL_SHEET = "Cash Flow {year}"
INCOME_TYPES = ("income", "refund")
CENT = Decimal("0.01")


class RecurringError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- months
def first(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    i = d.year * 12 + d.month - 1 + n
    return date(i // 12, i % 12 + 1, 1)


def months(start: date, end: date) -> list[date]:
    out, m = [], first(start)
    while m <= first(end):
        out.append(m)
        m = add_months(m, 1)
    return out


def _log(
    db: Session, table: str, row_id: int, column: str, old: object, new: object, why: str, user: str
) -> None:
    if old != new:
        db.add(
            ChangeLog(
                table_name=table,
                row_id=row_id,
                column_name=column,
                old_value=None if old is None else str(old)[:400],
                new_value=None if new is None else str(new)[:400],
                reason=why,
                changed_by=user,
            )
        )


# ---------------------------------------------------------------- templates and amounts
def amounts(db: Session, template_ids: list[int] | None = None) -> dict[int, list[RecurringAmount]]:
    q = select(RecurringAmount).order_by(RecurringAmount.from_month)
    if template_ids is not None:
        q = q.where(RecurringAmount.template_id.in_(template_ids))
    out: dict[int, list[RecurringAmount]] = defaultdict(list)
    for a in db.scalars(q):
        out[a.template_id].append(a)
    return out


def amount_for(history: list[RecurringAmount], month: date) -> Decimal | None:
    """The amount in force in a month: the latest change on or before it."""
    hit = None
    for a in history:
        if a.from_month <= month:
            hit = a.amount
    return hit


def active_in(t: RecurringTemplate, month: date) -> bool:
    return t.is_active and t.start_month <= month and (t.end_month is None or month <= t.end_month)


def signed(type_: str, amount: Decimal) -> Decimal:
    """Templates are entered as positive numbers; income is money in, everything else out."""
    value = abs(amount)
    return value if type_ in INCOME_TYPES else -value


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
) -> RecurringTemplate:
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


def get_template(db: Session, template_id: int) -> RecurringTemplate:
    t = db.get(RecurringTemplate, template_id)
    if t is None:
        raise RecurringError(f"Template {template_id} not found.", 404)
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
)


def update_template(db: Session, template_id: int, changes: dict[str, object], user: str) -> None:
    t = get_template(db, template_id)
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        clash = db.scalar(
            select(RecurringTemplate).where(
                RecurringTemplate.name == name, RecurringTemplate.template_id != template_id
            )
        )
        if not name or clash:
            raise RecurringError("Choose a name no other template has.", 409 if clash else 422)
        changes["name"] = name
    if "match_pattern" in changes:
        changes["match_pattern"] = str(changes["match_pattern"] or "").strip() or None
    if changes.get("end_month") is not None:
        end = first(changes["end_month"])  # type: ignore[arg-type]
        if end < t.start_month:
            raise RecurringError("The last month is before the first month.")
        changes["end_month"] = end
    if "type" in changes and changes["type"] != t.type:
        # Income and expense flip the sign of every amount kept.
        for a in amounts(db, [template_id])[template_id]:
            a.amount = signed(str(changes["type"]), a.amount)
        for e in db.scalars(
            select(RecurringEntry).where(RecurringEntry.template_id == template_id)
        ):
            e.amount = signed(str(changes["type"]), e.amount)
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


def delete_template(db: Session, template_id: int, user: str) -> None:
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
    from_month, to_start, to_end = first(from_month), first(to_start), first(to_end)
    if to_end < to_start:
        raise RecurringError("The range ends before it starts.")
    if to_start <= from_month <= to_end:
        raise RecurringError("Copy to other months than the one you copy from.")
    if len(months(to_start, to_end)) > 36:
        raise RecurringError("Copy to at most 36 months at a time.")
    q = select(RecurringEntry).where(RecurringEntry.month == from_month)
    if template_ids:
        q = q.where(RecurringEntry.template_id.in_(template_ids))
    sources = list(db.scalars(q))
    if not sources:
        raise RecurringError(f"{from_month:%B %Y} has no entries to copy; generate it first.")
    history = amounts(db)
    linked = _linked_entry_ids(db)
    written = 0
    for m in months(to_start, to_end):
        existing = {
            e.template_id: e
            for e in db.scalars(select(RecurringEntry).where(RecurringEntry.month == m))
        }
        for src in sources:
            target = existing.get(src.template_id)
            if target is not None and target.entry_id in linked:
                continue
            default = amount_for(history[src.template_id], m)
            if target is None:
                target = RecurringEntry(template_id=src.template_id, month=m, amount=src.amount)
                db.add(target)
            target.amount = src.amount
            target.status = src.status
            target.is_override = src.amount != default
            written += 1
    db.commit()
    for m in months(to_start, to_end):
        match(db, m, user)
    return written


def get_entry(db: Session, entry_id: int) -> RecurringEntry:
    e = db.get(RecurringEntry, entry_id)
    if e is None:
        raise RecurringError(f"Entry {entry_id} not found.", 404)
    return e


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
    e = get_entry(db, entry_id)
    _unlink_lines(db, [entry_id], user, "Entry removed")
    _log(db, "core.recurring_entry", entry_id, "amount", e.amount, None, "Removed", user)
    db.delete(e)
    db.commit()


# ---------------------------------------------------------------- links
def _linked_entry_ids(db: Session) -> set[int]:
    return set(
        db.scalars(
            select(Transaction.recurring_entry_id)
            .where(Transaction.recurring_entry_id.is_not(None))
            .distinct()
        )
    )


def _set_link(db: Session, t: Transaction, entry_id: int | None, user: str, why: str) -> None:
    _log(
        db,
        "core.transaction",
        t.transaction_id,
        "recurring_entry_id",
        t.recurring_entry_id,
        entry_id,
        why,
        user,
    )
    t.recurring_entry_id = entry_id


def _unlink_lines(db: Session, entry_ids: list[int], user: str, why: str) -> int:
    lines = list(
        db.scalars(select(Transaction).where(Transaction.recurring_entry_id.in_(entry_ids)))
    )
    for t in lines:
        _set_link(db, t, None, user, why)
    return len(lines)


def unlink_line(db: Session, transaction_id: int, user: str) -> None:
    t = db.get(Transaction, transaction_id)
    if t is None or t.recurring_entry_id is None:
        raise RecurringError("That line isn't linked to a recurring entry.", 404)
    _set_link(db, t, None, user, "Not this recurring item")
    db.commit()


def link_line(db: Session, entry_id: int, transaction_id: int, user: str) -> None:
    e = get_entry(db, entry_id)
    t = db.get(Transaction, transaction_id)
    if t is None:
        raise RecurringError(f"Transaction {transaction_id} not found.", 404)
    if t.cash_month != e.month:
        raise RecurringError("The line is in another month than the entry.")
    if _has_parts(db, t.transaction_id):
        raise RecurringError("The line is split; link its parts instead.")
    _set_link(db, t, entry_id, user, "Linked by hand")
    if e.status == "skipped":
        e.status = "planned"
    db.commit()


def _has_parts(db: Session, transaction_id: int) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.parent_transaction_id == transaction_id)
        )
    )


def candidates(db: Session, entry_id: int) -> list[Transaction]:
    """Lines of the entry's month that are free to link, closest amounts first."""
    e = get_entry(db, entry_id)
    t = get_template(db, e.template_id)
    rows = [r for r in _free_lines(db, e.month) if (r.amount > 0) == (e.amount > 0)]
    rows.sort(key=lambda r: (r.category_id != t.category_id, abs(r.amount - e.amount)))
    return rows[:25]


def _free_lines(db: Session, month: date) -> list[Transaction]:
    part = aliased(Transaction)
    has_parts = exists().where(part.parent_transaction_id == Transaction.transaction_id)
    return list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.cash_month == month,
                Transaction.recurring_entry_id.is_(None),
                ~has_parts,
            )
            .order_by(Transaction.txn_date, Transaction.transaction_id)
        )
    )


# ---------------------------------------------------------------- matching
def tolerance(t: RecurringTemplate, expected: Decimal) -> Decimal:
    return max(abs(expected) * t.tolerance_pct / 100, MIN_TOLERANCE)


@dataclass
class _Line:
    row: Transaction
    excel_key: tuple[str, str, str] | None
    accounts: set[int] = field(default_factory=set)


def _excel_key(block: str | None, group: str | None, label: str | None) -> tuple[str, str, str]:
    return (norm(block), norm(group), norm(label))


def _template_key(t: RecurringTemplate) -> tuple[str, str, str] | None:
    if t.excel_label is None:
        return None
    return _excel_key(t.excel_block, t.excel_group, t.excel_label)


def _eligible(t: RecurringTemplate, ln: _Line) -> bool:
    key = _template_key(t)
    if ln.excel_key is not None and key is not None:
        return ln.excel_key == key
    # An uncategorized line qualifies through the template's pattern; else the category decides.
    if ln.row.category_id is None:
        if not t.match_pattern:
            return False
    elif ln.row.category_id != t.category_id:
        return False
    if t.account_id is not None and t.account_id not in ln.accounts:
        return False
    pattern = (t.match_pattern or "").casefold()
    return pattern in ln.row.description_raw.casefold()


def excel_months(db: Session) -> set[date]:
    return set(
        db.scalars(
            select(Transaction.cash_month).where(Transaction.source == "excel_history").distinct()
        )
    )


def match(db: Session, month: date, user: str = "system") -> int:
    """Link the month's free lines to its planned entries that have no lines yet."""
    month = first(month)
    linked = _linked_entry_ids(db)
    entries = [
        e
        for e in db.scalars(
            select(RecurringEntry).where(
                RecurringEntry.month == month, RecurringEntry.status == "planned"
            )
        )
        if e.entry_id not in linked
    ]
    if not entries:
        return 0
    templates = {t.template_id: t for t in db.scalars(select(RecurringTemplate))}
    from_excel = month in excel_months(db)
    rows = [r for r in _free_lines(db, month) if (r.source == "excel_history") == from_excel]
    cells = {
        c.cell_id: c
        for c in db.scalars(
            select(ExcelCell).where(
                ExcelCell.cell_id.in_([r.excel_cell_id for r in rows if r.excel_cell_id])
            )
        )
    }
    partners = _partner_accounts(db, rows)
    lines = []
    for r in rows:
        cell = cells.get(r.excel_cell_id or -1)
        key = _excel_key(cell.block, cell.group_label, cell.row_label) if cell else None
        accounts = {a for a in (r.account_id, partners.get(r.transaction_id)) if a is not None}
        lines.append(_Line(r, key, accounts))

    taken: set[int] = set()
    count = 0

    def link(e: RecurringEntry, chosen: list[_Line]) -> None:
        nonlocal count
        for ln in chosen:
            _set_link(db, ln.row, e.entry_id, user, "Recurring match")
            taken.add(ln.row.transaction_id)
        count += len(chosen)

    # 1. Workbook rows link to the template made from them, whatever the amount.
    pending = []
    for e in entries:
        t = templates[e.template_id]
        exact = [
            ln
            for ln in lines
            if ln.excel_key is not None
            and ln.excel_key == _template_key(t)
            and ln.row.transaction_id not in taken
        ]
        if exact:
            link(e, exact)
        else:
            pending.append(e)

    # 2. The most specific templates first (account or pattern), then the largest amounts.
    def order(e: RecurringEntry) -> tuple[int, Decimal]:
        t = templates[e.template_id]
        specific = (t.account_id is not None) + bool(t.match_pattern)
        return (-specific, -abs(e.amount))

    pending.sort(key=order)
    options = {
        e.entry_id: [ln for ln in lines if _eligible(templates[e.template_id], ln)] for e in pending
    }
    for e in pending:
        t = templates[e.template_id]
        free = [ln for ln in options[e.entry_id] if ln.row.transaction_id not in taken]
        if not free:
            continue
        tol = tolerance(t, e.amount)
        best = min(free, key=lambda ln: (abs(ln.row.amount - e.amount), ln.row.transaction_id))
        if abs(best.row.amount - e.amount) <= tol:
            link(e, [best])
            continue
        others = [o for o in pending if o is not e]
        exclusive = [
            ln
            for ln in free
            if not any(ln in options[o.entry_id] for o in others)
            and (ln.row.amount > 0) == (e.amount > 0)
        ]
        if len(exclusive) > 1 and abs(sum(ln.row.amount for ln in exclusive) - e.amount) <= tol:
            link(e, exclusive)
    db.commit()
    return count


def _partner_accounts(db: Session, rows: list[Transaction]) -> dict[int, int]:
    """The account on the other side of each matched transfer (a card payment's card)."""
    groups = {r.transfer_group_id for r in rows if r.transfer_group_id is not None}
    if not groups:
        return {}
    legs = list(db.scalars(select(Transaction).where(Transaction.transfer_group_id.in_(groups))))
    out = {}
    for r in rows:
        for o in legs:
            if (
                o.transfer_group_id == r.transfer_group_id
                and o.transaction_id != r.transaction_id
                and o.account_id is not None
            ):
                out[r.transaction_id] = o.account_id
    return out


def match_all(db: Session, user: str = "system") -> int:
    found = db.scalars(
        select(RecurringEntry.month).where(RecurringEntry.status == "planned").distinct()
    )
    return sum(match(db, m, user) for m in sorted(found))


# ---------------------------------------------------------------- grid
@dataclass
class Cell:
    month: date
    entry_id: int | None
    expected: Decimal | None
    actual: Decimal | None
    lines: int
    status: str  # matched, planned, skipped, not_generated, none
    is_override: bool
    notes: str | None


@dataclass
class Row:
    template: RecurringTemplate
    group: str
    cells: list[Cell]


@dataclass
class Grid:
    year: int
    months: list[date]
    rows: list[Row]
    excel_months: list[date]


def grid(db: Session, year: int) -> Grid:
    ms = months(date(year, 1, 1), date(year, 12, 1))
    entries = list(
        db.scalars(
            select(RecurringEntry).where(
                RecurringEntry.month >= ms[0], RecurringEntry.month <= ms[-1]
            )
        )
    )
    by_cell = {(e.template_id, e.month): e for e in entries}
    actual: dict[int, Decimal] = defaultdict(Decimal)
    count: dict[int, int] = defaultdict(int)
    if entries:
        for entry_id, amount in db.execute(
            select(Transaction.recurring_entry_id, Transaction.amount).where(
                Transaction.recurring_entry_id.in_([e.entry_id for e in entries])
            )
        ):
            if entry_id is not None:
                actual[entry_id] += amount
                count[entry_id] += 1
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    history = amounts(db)
    used = {e.template_id for e in entries}
    rows = []
    for t in db.scalars(
        select(RecurringTemplate).order_by(RecurringTemplate.sort_order, RecurringTemplate.name)
    ):
        if t.template_id not in used and not any(active_in(t, m) for m in ms):
            continue
        cells = []
        for m in ms:
            e = by_cell.get((t.template_id, m))
            if e is not None:
                status = "matched" if count[e.entry_id] else e.status
                cells.append(
                    Cell(
                        m,
                        e.entry_id,
                        e.amount,
                        actual[e.entry_id] if count[e.entry_id] else None,
                        count[e.entry_id],
                        status,
                        e.is_override,
                        e.notes,
                    )
                )
            elif active_in(t, m):
                cells.append(
                    Cell(
                        m,
                        None,
                        amount_for(history[t.template_id], m),
                        None,
                        0,
                        "not_generated",
                        False,
                        None,
                    )
                )
            else:
                cells.append(Cell(m, None, None, None, 0, "none", False, None))
        cat = cats.get(t.category_id)
        parent = cats.get(cat.parent_id) if cat and cat.parent_id else None
        group = t.excel_group or (parent.name if parent else cat.name if cat else "")
        rows.append(Row(t, group, cells))
    covered = sorted(m for m in excel_months(db) if m.year == year)
    return Grid(year, ms, rows, covered)


def plan_by_month(db: Session) -> dict[date, tuple[Decimal, Decimal]]:
    """Expected income and outflows per month from the planned entries (skips left out)."""
    out: dict[date, list[Decimal]] = {}
    q = (
        select(RecurringEntry.month, RecurringTemplate.type, func.sum(RecurringEntry.amount))
        .join(RecurringTemplate, RecurringTemplate.template_id == RecurringEntry.template_id)
        .where(RecurringEntry.status == "planned")
        .group_by(RecurringEntry.month, RecurringTemplate.type)
    )
    for month, type_, total in db.execute(q):
        item = out.setdefault(month, [Decimal(0), Decimal(0)])
        value = Decimal(str(total))
        if type_ in INCOME_TYPES:
            item[0] += value
        else:
            item[1] -= value
    return {m: (v[0], v[1]) for m, v in out.items()}


# ---------------------------------------------------------------- from the workbook
@dataclass
class ExcelRow:
    block: str
    group: str | None
    label: str
    name: str
    category_id: int | None
    category_path: str | None
    type: str | None
    person: str | None
    values: dict[date, Decimal]  # signed, by month
    suggested: bool
    exists: bool


def _paths(db: Session) -> dict[str, int]:
    cats = list(db.scalars(select(Category)))
    by_id = {c.category_id: c for c in cats}
    out = {}
    for c in cats:
        parent = by_id.get(c.parent_id) if c.parent_id is not None else None
        out[f"{parent.name}/{c.name}" if parent else c.name] = c.category_id
    return out


def excel_rows(db: Session, year: int) -> list[ExcelRow]:
    """The year's income and expense rows from the latest loaded workbook, in sheet order. A row
    is suggested when it has a value in at least three months or a planned value."""
    sheet = EXCEL_SHEET.format(year=year)
    import_id = db.scalar(select(func.max(ExcelCell.import_id)).where(ExcelCell.sheet == sheet))
    if import_id is None:
        return []
    cells = list(
        db.scalars(
            select(ExcelCell)
            .where(
                ExcelCell.import_id == import_id,
                ExcelCell.sheet == sheet,
                ExcelCell.block.in_(("income", "expense")),
                ExcelCell.month.is_not(None),
            )
            .order_by(ExcelCell.cell_id)
        )
    )
    paths = _paths(db)
    plan_from = max(excel_months(db), default=date(year, 1, 1))
    existing = {_template_key(t) for t in db.scalars(select(RecurringTemplate)) if t.excel_label}
    rows: dict[tuple[str, str, str], ExcelRow] = {}
    for c in cells:
        key = _excel_key(c.block, c.group_label, c.row_label)
        row = rows.get(key)
        if row is None:
            mapping = lookup(c.block, c.group_label, c.row_label)
            row = ExcelRow(
                block=c.block,
                group=c.group_label,
                label=c.row_label.strip(),
                name=c.row_label.strip(),
                category_id=paths.get(mapping.category) if mapping else None,
                category_path=mapping.category.replace("/", " / ") if mapping else None,
                type=mapping.type if mapping else None,
                person=mapping.person if mapping else None,
                values={},
                suggested=False,
                exists=key in existing,
            )
            rows[key] = row
        assert c.month is not None
        value = c.value if row.type == "income" else -c.value
        if value:
            row.values[c.month] = row.values.get(c.month, Decimal(0)) + value
    labels: dict[str, int] = defaultdict(int)
    for r in rows.values():
        labels[norm(r.label)] += 1
    out = []
    for r in rows.values():
        if not r.values:
            continue
        if labels[norm(r.label)] > 1 and r.group:
            r.name = f"{r.label} ({r.group.strip()})"
        planned = any(m > plan_from for m in r.values)
        r.suggested = (len(r.values) >= 3 or planned) and not r.exists and r.category_id is not None
        out.append(r)
    return out


def create_from_excel(db: Session, year: int, names: list[str], user: str) -> tuple[int, int, int]:
    """Make templates from the chosen workbook rows and fill the year: one entry per month with a
    value (the workbook's amount), then link the Excel history. Returns (templates, entries,
    lines linked)."""
    rows = {r.name: r for r in excel_rows(db, year)}
    unknown = [n for n in names if n not in rows]
    if unknown:
        raise RecurringError(f"Not rows of the {year} sheet: {', '.join(unknown)}.")
    order = list(rows)
    made = entries = 0
    for name in sorted(names, key=order.index):
        r = rows[name]
        if r.exists:
            continue
        if r.category_id is None or r.type is None:
            raise RecurringError(f"{name} has no category mapping.")
        ms = sorted(r.values)
        latest = r.values[ms[-1]]
        t = create_template(
            db,
            name=_unique_name(db, r.name),
            category_id=r.category_id,
            type_=r.type,
            amount=latest,
            start_month=ms[0],
            user=user,
            person=r.person,
            sort_order=order.index(name) + 1,
            source="excel",
            excel=(r.block, r.group, r.label),
        )
        for m in ms:
            value = r.values[m]
            db.add(
                RecurringEntry(
                    template_id=t.template_id, month=m, amount=value, is_override=value != latest
                )
            )
            entries += 1
        made += 1
    db.commit()
    linked = sum(match(db, m, user) for m in months(date(year, 1, 1), date(year, 12, 1)))
    return made, entries, linked


def _unique_name(db: Session, name: str) -> str:
    candidate, n = name[:100], 2
    while db.scalar(select(RecurringTemplate).where(RecurringTemplate.name == candidate)):
        candidate = f"{name[:95]} ({n})"
        n += 1
    return candidate
