"""The weekly digest (ADR-038): what changed and what needs someone, in one email on Monday
morning. The Gmail script fetches it from GET /api/inbox (the inbox token) and sends it from
Hernan's Gmail, so the app needs no mail service. Only things that need action are alerts:
lines without a category, bills due this week or late, cash running short, unusually large
charges, statements still missing and invoices to sort out for gastos personales."""

import html
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Transaction
from app.services import cashflow, classify, gastos, projections, recurring, report
from app.services.recurring import add_months, first

ZERO = Decimal(0)
MINUS = "\u2212"
BIG = Decimal(50)  # a charge must be at least this to be called unusual
TIMES = Decimal(3)  # ... and this many times the merchant's usual amount


def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _money(v: Decimal) -> str:
    return f"{MINUS if v < 0 else ''}${abs(v):,.2f}"


@dataclass
class Item:
    """One thing to do, with where to do it."""

    text: str
    link: str  # a path in the app


@dataclass
class Section:
    """A group of things to do."""

    title: str
    items: list[Item] = field(default_factory=list)


@dataclass
class Digest:
    """The daily check-in: a summary and its sections."""

    today: date
    subject: str
    summary: str
    sections: list[Section]

    @property
    def actions(self) -> int:
        """How many things the digest asks for."""
        return sum(len(s.items) for s in self.sections)


def _spent(db: Session, start: date, end: date) -> Decimal:
    """Money out between two days (inclusive), counted like the cash flow."""
    t = Transaction
    q = cashflow.counted(
        select(func.coalesce(func.sum(t.amount), 0)).where(
            t.txn_date >= start, t.txn_date <= end, t.amount < 0, t.type != "income"
        )
    )
    return -Decimal(db.scalar(q) or 0)


def _unusual(db: Session, today: date) -> list[Item]:
    """Charges of the last 7 days at least $50 and 3 times the merchant's usual (its median over
    the 6 months before)."""
    t = Transaction
    week = today - timedelta(days=7)
    recent = list(
        db.scalars(
            select(t).where(
                t.txn_date > week, t.txn_date <= today, t.amount <= -BIG, t.type != "transfer"
            )
        )
    )
    out = []
    for r in recent:
        if not r.merchant:
            continue
        before = [
            -a
            for a in db.scalars(
                select(t.amount).where(
                    t.merchant == r.merchant,
                    t.amount < 0,
                    t.txn_date < r.txn_date,
                    t.txn_date >= r.txn_date - timedelta(days=183),
                )
            )
        ]
        if len(before) < 2:
            continue
        usual = Decimal(median(before))
        if usual > 0 and -r.amount >= usual * TIMES:
            out.append(
                Item(
                    f"{r.merchant}: {_money(-r.amount)} on {r.txn_date:%b %d}, "
                    f"usually about {_money(usual)}",
                    f"/transactions?q={r.merchant}",
                )
            )
    return out[:5]


SOON_DAYS = 7  # bills due within this many days are shown
MAX_BILLS = 8
MAX_MISSING = 6
SAFE_DAY = 28  # a day every month has


def _inbox(db: Session, today: date) -> Section | None:
    waiting = classify.uncategorized(db)
    if not waiting:
        return None
    merchants = len({classify.merchant_key(t.description_raw) for t in waiting})
    text = f"{_n(len(waiting), 'line')} from {_n(merchants, 'merchant')} in the Inbox"
    return Section("Needs a category", [Item(text, "/review")])


def _bills(db: Session, today: date) -> Section | None:
    """Bills late this month, or due in the next days."""
    soon = today + timedelta(days=SOON_DAYS)
    items = []
    for m in {first(today), first(soon)}:
        for b in recurring.bills(db, m, today):
            if b.type in ("income", "refund") or b.status in ("paid", "skipped"):
                continue
            if b.status == "late":
                items.append(Item(f"Late: {b.name}, {_money(abs(b.expected))}", "/recurring"))
                continue
            due = m.replace(day=min(b.due_day, SAFE_DAY)) if b.due_day else None
            if due is not None and today <= due <= soon:
                where = f" from {b.account_name}" if b.account_name else ""
                text = f"{b.name}: {_money(abs(b.expected))} due {due:%a %b %d}{where}"
                items.append(Item(text, "/recurring"))
    return Section("Bills this week", items[:MAX_BILLS]) if items else None


def _cash(db: Session, today: date) -> Section | None:
    """Accounts, or cash as a whole, going under the floor in the next month."""
    p = projections.project(db, today, horizon=1)
    items = [
        Item(
            f"{a.name} dips to {_money(a.lowest[1])} on {a.lowest[0]:%b %d}: "
            f"move {_money(a.move)} in before {a.under_floor:%b %d}",
            "/projections",
        )
        for a in p.accounts
        if a.under_floor
    ]
    if not items and p.first_short and p.lowest:
        items.append(
            Item(
                f"Total cash goes under zero on {p.first_short:%b %d} "
                f"(lowest {_money(p.lowest[1])})",
                "/projections",
            )
        )
    return Section("Cash running short", items) if items else None


def _odd_charges(db: Session, today: date) -> Section | None:
    odd = _unusual(db, today)
    return Section("Unusual charges this week", odd) if odd else None


def _missing_statements(db: Session, today: date) -> Section | None:
    """Statements still missing for last month (this month's aren't due yet)."""
    last_month = add_months(first(today), -1)
    missing = [Item(t, "/status") for t in report._status(db, last_month, today)["open"]]
    return Section("Statements to bring in", missing[:MAX_MISSING]) if missing else None


def _deductions(db: Session, today: date) -> Section | None:
    g = gastos.summary(db, today.year)
    to_sort = sum(x.to_classify for x in g.people) + g.unassigned
    if not to_sort:
        return None
    text = f"{_n(to_sort, 'invoice')} to sort out for {today.year}"
    return Section("Gastos personales", [Item(text, "/taxes")])


def _month_so_far(db: Session, today: date) -> str:
    """The month's spending so far, against the same days last month."""
    month = first(today)
    now = _spent(db, month, today)
    prev_month = add_months(month, -1)
    prev_end = prev_month.replace(day=min(today.day, 28 if prev_month.month == 2 else 30))
    before = _spent(db, prev_month, prev_end)
    change = ""
    if before:
        pct = (now - before) / before * 100
        change = (
            f", {'+' if pct >= 0 else MINUS}{abs(pct):.0f}% vs the same days of {prev_month:%B}"
        )
    return f"Spent {_money(now)} in {month:%B} so far{change}."


# The sections, in the order the check-in shows them.
SECTIONS = (_inbox, _bills, _cash, _odd_charges, _missing_statements, _deductions)


def build(db: Session, today: date | None = None) -> Digest:
    """The daily check-in: what needs a decision today, by section, with one summary line."""
    today = today or date.today()
    sections = [s for make in SECTIONS if (s := make(db, today)) is not None]
    actions = sum(len(s.items) for s in sections)
    need = f"{actions} {'thing needs' if actions == 1 else 'things need'} you"
    subject = f"Cashflow, week of {today:%b %d}: {need if actions else 'all clear'}"
    return Digest(today, subject, _month_so_far(db, today), sections)


def text(d: Digest, base_url: str) -> str:
    """The digest as the plain text of its email, with links under `base_url`."""
    lines = [d.summary, ""]
    for s in d.sections:
        lines.append(s.title.upper())
        lines += [f"- {i.text}" for i in s.items]
        lines.append("")
    if not d.sections:
        lines.append("Nothing needs you this week.")
    lines.append(f"Open the app: {base_url}")
    return "\n".join(lines)


def to_html(d: Digest, base_url: str) -> str:
    """A plain email in the Clear look: near-black text, green links, no images."""
    e = html.escape
    parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#0b0f19;font-size:15px;'
        'line-height:1.5;max-width:560px">',
        f'<p style="font-size:17px;margin:0 0 16px">{e(d.summary)}</p>',
    ]
    for s in d.sections:
        parts.append(
            f'<h2 style="font-size:15px;margin:20px 0 6px;color:#0b0f19">{e(s.title)}</h2><ul '
            'style="margin:0;padding-left:20px">'
        )
        for i in s.items:
            parts.append(
                f'<li><a style="color:#047857" href="{e(base_url + i.link)}">{e(i.text)}</a></li>'
            )
        parts.append("</ul>")
    if not d.sections:
        parts.append("<p>Nothing needs you this week.</p>")
    parts.append(
        f'<p style="margin-top:24px;color:#475467;font-size:13px">'
        f'<a style="color:#047857" href="{e(base_url)}">Open Cashflow</a></p></div>'
    )
    return "".join(parts)
