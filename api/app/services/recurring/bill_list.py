"""Bills: every recurring item due in a month, whether it was paid, and when it is due."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Category,
    ImportBatch,
    LoadLog,
    RecurringAmount,
    RecurringEntry,
    RecurringTemplate,
    StatementFileAccount,
    StatementHeader,
    Transaction,
)
from app.services.recurring.base import (
    active_in,
    add_months,
    amount_for,
    amounts,
    due_in,
    first,
    months,
)


# ---------------------------------------------------------------- bills (ADR-031)
@dataclass
class Bill:
    """A bill in a month: what is expected, when, and whether it was paid."""

    template_id: int
    entry_id: int | None  # this month's entry, when the month was generated
    name: str
    type: str
    group: str
    group_color: str | None
    category_path: str
    account_name: str | None
    every_months: int
    due_day: int | None  # set, or read from the lines it matched; None when neither
    due_day_set: bool
    expected: Decimal  # signed, like transactions
    paid: Decimal | None  # matched lines, signed
    lines: int
    status: str  # paid, due, late, skipped
    avg3: Decimal | None  # matched in the three months before, average (signed)
    payments_left: int | None  # with an end month: this one and the ones after
    price_from: Decimal | None  # the amount before its latest change, when it changed lately
    price_changed: date | None
    end_month: date | None


PRICE_RECENT = 6  # months a price change is shown for
IN_CHUNK = 1000  # ids in one IN (...): SQL Server allows 2,100 parameters a query


def _usual_day(days: list[int]) -> int | None:
    if not days:
        return None
    s = sorted(days)
    return s[len(s) // 2]


def _due_date(month: date, due_day: int | None) -> date:
    """The day a bill of `month` is due; the month's last day when it has none or the month is
    shorter."""
    last = (add_months(first(month), 1) - timedelta(days=1)).day
    return first(month).replace(day=min(due_day or last, last))


def data_through(db: Session) -> dict[int, date]:
    """The last day each account's loaded data reaches (ADR-092): the end of its last approved
    statement, or the day of the last bank sync for an account the bank sync reads. An account
    with neither isn't in the answer."""
    out: dict[int, date] = {
        account_id: end
        for account_id, end in db.execute(
            select(StatementFileAccount.account_id, func.max(StatementHeader.period_end))
            .join(
                StatementHeader,
                StatementHeader.statement_file_id == StatementFileAccount.statement_file_id,
            )
            .join(
                ImportBatch, ImportBatch.statement_file_id == StatementFileAccount.statement_file_id
            )
            .where(ImportBatch.status == "approved")
            .group_by(StatementFileAccount.account_id)
        )
        if end is not None
    }
    synced = db.scalar(select(func.max(LoadLog.loaded_at)).where(LoadLog.source == "bank_sync"))
    if synced is not None:
        for (account_id,) in db.execute(
            select(Account.account_id).where(Account.sync_id.is_not(None))
        ).all():
            out[account_id] = max(out.get(account_id, synced.date()), synced.date())
    return out


@dataclass
class _Paid:
    """What the lines say about the entries around a month: what each entry was paid, with how
    many lines, and the days each template's lines fell on over the last year."""

    amount: dict[int, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    lines: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    days: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))


def _paid_lines(db: Session, month: date, entry_ids: set[int]) -> _Paid:
    """Read the lines matched over the year to `month`; amounts are kept for `entry_ids`."""
    year_entries = dict(
        db.execute(
            select(RecurringEntry.entry_id, RecurringEntry.template_id).where(
                RecurringEntry.month >= add_months(month, -12), RecurringEntry.month <= month
            )
        ).all()
    )
    out = _Paid()
    ids = list(year_entries)
    for start in range(0, len(ids), IN_CHUNK):
        for entry_id, amount, day in db.execute(
            select(Transaction.recurring_entry_id, Transaction.amount, Transaction.txn_date).where(
                Transaction.recurring_entry_id.in_(ids[start : start + IN_CHUNK])
            )
        ):
            if entry_id is None:
                continue
            out.days[year_entries[entry_id]].append(day.day)
            if entry_id in entry_ids:
                out.amount[entry_id] += amount
                out.lines[entry_id] += 1
    return out


def _bill_status(
    t: RecurringTemplate,
    e: RecurringEntry | None,
    lines: int,
    due: int | None,
    month: date,
    today: date,
    through: dict[int, date],
) -> str:
    """paid, skipped, due, late, or waiting: past its day and not seen, but the account that
    pays it has no data for that day yet (its statement hasn't arrived), so nobody can know."""
    if e is not None and e.status == "skipped" and not lines:
        return "skipped"
    if lines:
        return "paid"
    past = month < first(today) or (month == first(today) and due is not None and due < today.day)
    if not past:
        return "due"
    reach = through.get(t.account_id) if t.account_id else None
    return "waiting" if reach is not None and reach < _due_date(month, due) else "late"


def _price_change(
    history: list[RecurringAmount], month: date
) -> tuple[Decimal | None, date | None]:
    """The amount before the latest change and when it changed, when that was lately."""
    changes = [a for a in history if a.from_month <= month]
    if len(changes) >= 2 and changes[-1].from_month >= add_months(month, -PRICE_RECENT):
        return changes[-2].amount, changes[-1].from_month
    return None, None


def bills(db: Session, month: date, today: date | None = None) -> list[Bill]:
    """Every recurring item due in `month` (by how often it repeats), with whether a line paid
    it, the day it's due, the three months before and its latest price change."""
    month = first(month)
    today = today or date.today()
    window = [add_months(month, -i) for i in (3, 2, 1)]
    entries = list(
        db.scalars(
            select(RecurringEntry).where(
                RecurringEntry.month >= window[0], RecurringEntry.month <= month
            )
        )
    )
    by_cell = {(e.template_id, e.month): e for e in entries}
    paid = _paid_lines(db, month, {e.entry_id for e in entries})
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}
    history = amounts(db)
    through = data_through(db)
    out = []
    for t in db.scalars(
        select(RecurringTemplate).order_by(RecurringTemplate.sort_order, RecurringTemplate.name)
    ):
        e = by_cell.get((t.template_id, month))
        if e is None and not active_in(t, month):
            continue
        expected = e.amount if e is not None else amount_for(history[t.template_id], month)
        if expected is None:
            continue
        cat = cats.get(t.category_id)
        parent = cats.get(cat.parent_id) if cat and cat.parent_id else None
        path = f"{parent.name} / {cat.name}" if parent and cat else cat.name if cat else ""
        due = t.due_day or _usual_day(paid.days[t.template_id])
        n = paid.lines[e.entry_id] if e is not None else 0
        before = [
            paid.amount[x.entry_id]
            for m in window
            if (x := by_cell.get((t.template_id, m))) is not None and paid.lines[x.entry_id]
        ]
        price_from, price_changed = _price_change(history[t.template_id], month)
        out.append(
            Bill(
                template_id=t.template_id,
                entry_id=e.entry_id if e is not None else None,
                name=t.name,
                type=t.type,
                group=t.excel_group or (parent.name if parent else cat.name if cat else ""),
                group_color=(parent.color if parent else cat.color if cat else None),
                category_path=path,
                account_name=accounts.get(t.account_id) if t.account_id else None,
                every_months=t.every_months,
                due_day=due,
                due_day_set=t.due_day is not None,
                expected=expected,
                paid=paid.amount[e.entry_id] if e is not None and n else None,
                lines=n,
                status=_bill_status(t, e, n, due, month, today, through),
                avg3=(sum(before, Decimal(0)) / len(before)) if before else None,
                payments_left=(
                    sum(1 for m in months(month, t.end_month) if due_in(t, m))
                    if t.end_month is not None
                    else None
                ),
                price_from=price_from,
                price_changed=price_changed,
                end_month=t.end_month,
            )
        )
    return out
