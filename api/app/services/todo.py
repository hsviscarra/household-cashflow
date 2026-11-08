"""To do (ADR-047): everything that needs Hernan or Lauren, in one list, each with what to do
about it. It gathers what the Inbox, Data status, Net worth, Settings → Rules, the Recurring
page and Tax deductions each knew on their own, so nothing is missed by not opening a page."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category
from app.services import (
    bills_found,
    classify,
    gastos,
    inbox,
    loans,
    networth,
    rules_suggest,
    status,
    transfers,
)
from app.services.recurring import add_months, first

# How old a value may get before it's out of date (days), by kind: monthly statements, investments
# daily (priced), property and vehicles yearly. The page's freshness rule, kept in step.
FRESH_DAYS = {
    "cash": 45,
    "card": 45,
    "loan": 45,
    "purchase": 45,
    "investment": 10,
    "property": 365,
    "vehicle": 365,
    "other": 180,
}
MONTHS = 3  # months of Data status to look back on
MAX_TASKS = 25  # per section; the count says how many there are


@dataclass
class Task:
    key: str  # unique and stable, e.g. "cat:NETFLIX", "who:123"
    kind: str
    title: str
    detail: str = ""
    amount: Decimal | None = None
    on: date | None = None
    link: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Section:
    key: str
    title: str
    hint: str
    tasks: list[Task] = field(default_factory=list)
    count: int = 0  # how many things, which can be more than the tasks shown


@dataclass
class Todo:
    today: date
    sections: list[Section]

    @property
    def total(self) -> int:
        return sum(s.count for s in self.sections)


def _name(t: Any, accounts: dict[int, str]) -> str:
    return accounts.get(t.account_id, "") if t.account_id else ""


def _categorize(db: Session, accounts: dict[int, str], skip: set[int]) -> Section:
    sec = Section(
        "categorize",
        "Needs a category",
        "Pick a category; tick Always to make it a rule for the next statements too.",
    )
    groups = classify.review_groups(db)
    for g in groups:  # transfers that don't say who are asked once, under Who or what is it
        g.lines = [ln for ln in g.lines if ln.transaction_id not in skip]
    groups = [g for g in groups if g.lines]
    groups.sort(key=lambda g: (-len(g.lines), g.merchant_key))
    sec.count = sum(len(g.lines) for g in groups)
    for g in groups[:MAX_TASKS]:
        last = g.lines[-1]
        n = len(g.lines)
        sec.tasks.append(
            Task(
                key=f"cat:{g.merchant_key}",
                kind="categorize",
                title=g.merchant_key or last.description,
                detail=f"{n} line{'' if n == 1 else 's'} · last {last.txn_date:%b %d}"
                + (f" · {last.account_name}" if last.account_name else ""),
                amount=g.total,
                on=last.txn_date,
                link=f"/review?month={last.txn_date:%Y-%m}",
                data={
                    "merchant_key": g.merchant_key,
                    "transaction_ids": [ln.transaction_id for ln in g.lines],
                    "example": last.description,
                    "suggested_category_id": g.suggestion.category_id if g.suggestion else None,
                    "statement_file_id": last.statement_file_id,
                    "page": last.page,
                },
            )
        )
    return sec


def _who(db: Session, today: date, accounts: dict[int, str]) -> Section:
    sec = Section(
        "who",
        "Who or what is it",
        "Transfers that don't say who: choose the person, or a category such as Salary.",
    )
    rows = inbox.who_lines(db, today=today)
    sec.count = len(rows)
    for t in rows[:MAX_TASKS]:
        sec.tasks.append(
            Task(
                key=f"who:{t.transaction_id}",
                kind="who",
                title=t.description_raw,
                detail=f"{t.txn_date:%b %d} · {_name(t, accounts)}".rstrip(" ·"),
                amount=t.amount,
                on=t.txn_date,
                link=f"/transactions?q={t.transaction_id}",
                data={
                    "transaction_id": t.transaction_id,
                    "merchant_key": classify.merchant_key(t.description_raw),
                    "category_id": t.category_id,
                    "statement_file_id": t.statement_file_id,
                },
            )
        )
    return sec


def _transfers(db: Session, accounts: dict[int, str]) -> Section:
    sec = Section(
        "transfers",
        "Transfers missing the other side",
        "Money moved between your accounts but only one side is loaded; usually a statement "
        "still to bring in.",
    )
    rows = transfers.unmatched(db)
    sec.count = len(rows)
    for t in rows[:MAX_TASKS]:
        sec.tasks.append(
            Task(
                key=f"transfer:{t.transaction_id}",
                kind="transfer",
                title=t.description_raw,
                detail=f"{t.txn_date:%b %d} · {_name(t, accounts)}".rstrip(" ·"),
                amount=t.amount,
                on=t.txn_date,
                link=f"/review?month={t.txn_date:%Y-%m}",
                data={"transaction_id": t.transaction_id},
            )
        )
    return sec


def _books(db: Session, today: date) -> Section:
    """Statements to bring in, imports to approve, bills not paid, balance breaks: Data status
    for the last months, without what the sections above already list."""
    sec = Section(
        "books",
        "Statements, imports and bills",
        "What keeps the books from being complete.",
    )
    since = add_months(first(today), -(MONTHS - 1))
    seen: set[str] = set()
    for ms in status.month_status(db, today).months:
        if ms.month < since:
            continue
        for item in ms.items:
            if item.kind in ("uncategorized", "transfer") or item.text in seen:
                continue
            if item.kind == "statement" and ms.month == first(today):
                continue  # this month's statements aren't issued yet
            seen.add(item.text)
            sec.tasks.append(
                Task(
                    key=f"{item.kind}:{ms.month:%Y-%m}:{item.text}"[:200],
                    kind=item.kind,
                    title=item.text,
                    detail=f"{ms.month:%B %Y}",
                    link=item.link,
                )
            )
    sec.count = len(sec.tasks)
    sec.tasks = sec.tasks[:MAX_TASKS]
    return sec


def _values(db: Session, today: date) -> Section:
    sec = Section(
        "values",
        "Out-of-date values",
        "Balances and values older than they should be. An old workbook row next to a real "
        "account is probably the same money twice: pause it.",
    )
    items = [i for i in networth.sheet(db, today, months=1).items if i.is_active]
    for i in items:
        limit = FRESH_DAYS.get(i.holding_class)
        if limit is None or (i.holding_id is None and i.account_id is None):
            continue
        age = (today - i.as_of).days if i.as_of else None
        if age is not None and age <= limit:
            continue
        twin = None
        if i.source == "excel":
            twin = next(
                (
                    o.name
                    for o in items
                    if o.key != i.key and o.holding_class == i.holding_class and o.source != "excel"
                ),
                None,
            )
        since = f"{age} days old" if age is not None else "no value yet"
        sec.tasks.append(
            Task(
                key=f"value:{i.key}",
                kind="duplicate" if twin else "stale",
                title=i.name,
                detail=f"Probably the same money as {twin} · {since}" if twin else since,
                amount=i.value,
                on=i.as_of,
                link="/networth",
                data={"holding_id": i.holding_id, "account_id": i.account_id, "twin": twin},
            )
        )
    sec.tasks.sort(key=lambda t: (t.kind != "duplicate", t.on or date.min))
    sec.count = len(sec.tasks)
    sec.tasks = sec.tasks[:MAX_TASKS]
    return sec


def _loans(db: Session, today: date) -> Section:
    sec = Section(
        "loans",
        "Loan payments to confirm",
        "From the amortization table you loaded once: say Yes when it's paid and the balance "
        "updates. No new table needed.",
    )
    for h, row in loans.asks(db, today):
        sec.tasks.append(
            Task(
                key=f"loan:{h.holding_id}:{row.number}",
                kind="loan",
                title=f"Did you pay {h.name} installment {row.number}?",
                detail=f"{row.period:%B %Y} · principal {row.principal:,.2f}, interest "
                f"{row.interest:,.2f} · balance after {row.balance_after:,.2f}",
                amount=-row.total,
                on=row.period,
                link="/debt",
                data={"holding_id": h.holding_id, "number": row.number},
            )
        )
    sec.count = len(sec.tasks)
    return sec


def _suggestions(db: Session, today: date) -> Section:
    sec = Section(
        "suggestions",
        "Suggestions",
        "Rules and bills the app noticed from what you did; save them or let them go.",
    )
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    for s in rules_suggest.suggestions(db):
        c = cats.get(s.category_id)
        sec.tasks.append(
            Task(
                key=f"rule:{s.pattern}",
                kind="rule",
                title=f"Rule: {s.pattern}",
                detail=f"→ {c.name if c else '?'} · you chose it {s.times} times",
                link="/settings?tab=rules",
                data={
                    "pattern": s.pattern,
                    "category_id": s.category_id,
                    "person": s.person,
                },
            )
        )
    for b in bills_found.find(db, today):
        sec.tasks.append(
            Task(
                key=f"bill:{b.merchant}",
                kind="bill",
                title=f"Bill: {b.merchant}",
                detail=f"every {b.every_months} month{'s' if b.every_months > 1 else ''} · "
                f"around day {b.due_day} · {b.times} charges",
                amount=-b.amount,
                on=b.last_date,
                link="/recurring",
                data={
                    "merchant": b.merchant,
                    "category_id": b.category_id,
                    "account_id": b.account_id,
                    "person": b.person,
                    "match_pattern": b.match_pattern,
                    "every_months": b.every_months,
                    "due_day": b.due_day,
                    "amount": str(b.amount),
                    "last_date": b.last_date.isoformat(),
                },
            )
        )
    sec.count = len(sec.tasks)
    sec.tasks = sec.tasks[:MAX_TASKS]
    return sec


def _invoices(db: Session, today: date) -> Section:
    sec = Section(
        "invoices",
        "Tax deduction invoices",
        "SRI invoices without a person or a category this year.",
    )
    g = gastos.summary(db, today.year)
    n = sum(x.to_classify for x in g.people) + g.unassigned
    if n:
        sec.tasks.append(
            Task(
                key=f"invoices:{today.year}",
                kind="invoices",
                title=f"{n} invoice{'' if n == 1 else 's'} to sort out for {today.year}",
                link="/taxes",
            )
        )
    sec.count = n
    return sec


def build(db: Session, today: date | None = None) -> Todo:
    today = today or date.today()
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}
    who = _who(db, today, accounts)
    asked = {t.transaction_id for t in inbox.who_lines(db, today=today)}
    sections = [
        _categorize(db, accounts, asked),
        who,
        _books(db, today),
        _loans(db, today),
        _transfers(db, accounts),
        _values(db, today),
        _suggestions(db, today),
        _invoices(db, today),
    ]
    return Todo(today, [s for s in sections if s.count])
