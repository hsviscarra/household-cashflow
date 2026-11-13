"""Linking statement lines to the month's planned entries, by hand and by the matcher."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    ExcelCell,
    RecurringEntry,
    RecurringTemplate,
    Transaction,
    v_excel_month,
)
from app.services.excel_mapping import norm
from app.services.recurring.base import (
    MIN_TOLERANCE,
    RecurringError,
    _log,
    first,
    get_entry,
    get_template,
)


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
    """Undo a line's link to the entry it paid."""
    t = db.get(Transaction, transaction_id)
    if t is None or t.recurring_entry_id is None:
        raise RecurringError("That line isn't linked to a recurring entry.", 404)
    _set_link(db, t, None, user, "Not this recurring item")
    db.commit()


def link_line(db: Session, entry_id: int, transaction_id: int, user: str) -> None:
    """Say a line paid an entry; they must be in the same month."""
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
    """How far a line's amount may be from the expected one and still match: the item's
    percentage, at least MIN_TOLERANCE."""
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
    """Months where the workbook counts: those it covers before "statements from" (ADR-018)."""
    return set(db.scalars(select(v_excel_month.c.cash_month)))


@dataclass
class _Links:
    """The links one match makes: which lines are taken, and how many were linked."""

    db: Session
    user: str
    taken: set[int] = field(default_factory=set)
    count: int = 0

    def free(self, lines: list[_Line]) -> list[_Line]:
        """The lines nothing has taken yet."""
        return [ln for ln in lines if ln.row.transaction_id not in self.taken]

    def link(self, e: RecurringEntry, chosen: list[_Line]) -> None:
        """Link lines to an entry and take them."""
        for ln in chosen:
            _set_link(self.db, ln.row, e.entry_id, self.user, "Recurring match")
            self.taken.add(ln.row.transaction_id)
        self.count += len(chosen)


def _open_entries(db: Session, month: date) -> list[RecurringEntry]:
    """The month's planned entries that have no lines yet."""
    linked = _linked_entry_ids(db)
    return [
        e
        for e in db.scalars(
            select(RecurringEntry).where(
                RecurringEntry.month == month, RecurringEntry.status == "planned"
            )
        )
        if e.entry_id not in linked
    ]


def _match_lines(db: Session, month: date) -> list[_Line]:
    """The month's free lines, each with its workbook row and the accounts it touches. A
    workbook month matches workbook lines only, a statement month statement lines only."""
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
    return lines


def _link_workbook_rows(
    entries: list[RecurringEntry],
    templates: dict[int, RecurringTemplate],
    lines: list[_Line],
    links: _Links,
) -> list[RecurringEntry]:
    """Workbook rows link to the template made from them, whatever the amount. Returns the
    entries still without lines."""
    pending = []
    for e in entries:
        key = _template_key(templates[e.template_id])
        exact = [ln for ln in links.free(lines) if ln.excel_key is not None and ln.excel_key == key]
        if exact:
            links.link(e, exact)
        else:
            pending.append(e)
    return pending


def _link_by_amount(
    pending: list[RecurringEntry],
    templates: dict[int, RecurringTemplate],
    lines: list[_Line],
    links: _Links,
) -> None:
    """The most specific templates first (account or pattern), then the largest amounts: each
    takes the eligible line closest to its amount, or the lines only it can take when together
    they add up to it."""

    def order(e: RecurringEntry) -> tuple[int, Decimal]:
        t = templates[e.template_id]
        specific = (t.account_id is not None) + bool(t.match_pattern)
        return (-specific, -abs(e.amount))

    pending.sort(key=order)
    options = {
        e.entry_id: [ln for ln in lines if _eligible(templates[e.template_id], ln)] for e in pending
    }
    for e in pending:
        free = links.free(options[e.entry_id])
        if not free:
            continue
        tol = tolerance(templates[e.template_id], e.amount)
        best = min(free, key=lambda ln: (abs(ln.row.amount - e.amount), ln.row.transaction_id))
        if abs(best.row.amount - e.amount) <= tol:
            links.link(e, [best])
            continue
        others = [o for o in pending if o is not e]
        exclusive = [
            ln
            for ln in free
            if not any(ln in options[o.entry_id] for o in others)
            and (ln.row.amount > 0) == (e.amount > 0)
        ]
        if len(exclusive) > 1 and abs(sum(ln.row.amount for ln in exclusive) - e.amount) <= tol:
            links.link(e, exclusive)


def match(db: Session, month: date, user: str = "system") -> int:
    """Link the month's free lines to its planned entries that have no lines yet."""
    month = first(month)
    entries = _open_entries(db, month)
    if not entries:
        return 0
    templates = {t.template_id: t for t in db.scalars(select(RecurringTemplate))}
    lines = _match_lines(db, month)
    links = _Links(db, user)
    pending = _link_workbook_rows(entries, templates, lines, links)
    _link_by_amount(pending, templates, lines, links)
    db.commit()
    return links.count


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


def recategorized(db: Session, t: Transaction, user: str = "system") -> int:
    """After a person changes a line's category: free it from an entry of another category, then
    match its month again, so a rent line given its category counts as the rent paid."""
    if t.recurring_entry_id is not None:
        tpl = db.scalar(
            select(RecurringTemplate)
            .join(RecurringEntry, RecurringEntry.template_id == RecurringTemplate.template_id)
            .where(RecurringEntry.entry_id == t.recurring_entry_id)
        )
        if tpl is not None and tpl.category_id != t.category_id and t.source != "excel_history":
            _set_link(db, t, None, user, "Category changed")
            db.commit()
    if t.recurring_entry_id is None and t.cash_month is not None:
        return match(db, t.cash_month, user)
    return 0


def match_all(db: Session, user: str = "system") -> int:
    """Match every month that still has planned entries; returns how many matched."""
    found = db.scalars(
        select(RecurringEntry.month).where(RecurringEntry.status == "planned").distinct()
    )
    return sum(match(db, m, user) for m in sorted(found))
