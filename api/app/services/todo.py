"""To do (ADR-047): everything that needs Hernan or Lauren, in one list, each with what to do
about it. It gathers what the Inbox, Data status, Net worth, Settings → Rules, the Recurring
page and Tax deductions each knew on their own, so nothing is missed by not opening a page."""

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AppSetting, Category, Transaction
from app.services import (
    bills_found,
    classify,
    gastos,
    inbox,
    line_context,
    loans,
    networth,
    rules_suggest,
    sources,
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
# Words of descriptions that say nothing about who or what ("TRANSFERENCIA INTERNET", "SU PAGO
# MUCHAS GRACIAS"): a rule on them would catch unrelated payments, so Always is off for them.
GENERIC_WORDS = frozenset(
    (
        "TRANSFERENCIA",
        "TRANSFERENCIAS",
        "INTERNET",
        "SU",
        "PAGO",
        "PAGOS",
        "MUCHAS",
        "GRACIAS",
        "DEPOSITO",
        "DEPOSITOS",
        "TRANSFER",
        "ONLINE",
        "BANKING",
        "RETIRO",
        "CAJERO",
        "ATM",
        "NOTA",
        "CREDITO",
        "DEBITO",
        "ENVIADA",
        "RECIBIDA",
        "INTERBANCARIA",
        "INTERBANCARIO",
        "DE",
        "A",
        "POR",
        "EN",
        "MOVIL",
        "BANCA",
        "WEB",
        "TO",
        "FROM",
        "PAYMENT",
        "MOBILE",
        "CTA",
        "CTAS",
        "CUENTA",
        "CUENTAS",
        "TERCEROS",
        "TERCERO",
        "BCA",
        "BCO",
        "BANCO",
        "BANCOS",
        "ENL",
        "LINEA",
        "OTROS",
        "OTRAS",
        "ENVIO",
        "ENVIADO",
        "SPI",
        "DIRECTO",
        "DIRECTA",
        "INTERNA",
        "INTERNO",
        "PROPIAS",
        "PROPIA",
        "AHORROS",
        "CORRIENTE",
        "TRANSF",
        "TRF",
        "ZELLE",
    )
)
DISMISSED = "todo-dismissed:"  # core.app_setting keys of tasks let go (ADR-058)


def rule_ok(merchant_key: str | None) -> bool:
    """Whether a rule on this description would be safe: it names someone or something."""
    words = (merchant_key or "").upper().replace("*", " ").split()
    return bool(words) and not all(w in GENERIC_WORDS for w in words)


def _dismiss_key(task_key: str) -> str:
    return DISMISSED + hashlib.sha1(task_key.encode()).hexdigest()[:32]


def dismiss(db: Session, task_key: str, user: str) -> None:
    """Let a suggestion or an out-of-date value go: it isn't asked again."""
    k = _dismiss_key(task_key)
    if db.get(AppSetting, k) is None:
        db.add(AppSetting(setting_key=k, setting_value=task_key[:200], updated_by=user[:200]))
        db.commit()


def _dismissed(db: Session) -> set[str]:
    return {
        s.setting_key
        for s in db.scalars(select(AppSetting).where(AppSetting.setting_key.startswith(DISMISSED)))
    }


@dataclass
class Task:
    """One thing to do, with its amount, date and link."""

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
    """A kind of task, with its tasks."""

    key: str
    title: str
    hint: str
    tasks: list[Task] = field(default_factory=list)
    count: int = 0  # how many things, which can be more than the tasks shown


@dataclass
class Todo:
    """Everything to do today."""

    today: date
    sections: list[Section]

    @property
    def total(self) -> int:
        """How many things there are to do."""
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
    groups.sort(key=lambda g: (-abs(g.total), g.merchant_key))  # most money at stake first
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
                    "rule_ok": rule_ok(g.merchant_key),
                    "statement_file_id": last.statement_file_id,
                    "page": last.page,
                },
            )
        )
    return sec


def _at_stake(t: Transaction) -> tuple[Decimal, int]:
    """Sort key: the most money first (ADR-089), the newest line first among equals."""
    return (-abs(t.amount), -t.transaction_id)


def _who(rows: list[Transaction], accounts: dict[int, str]) -> Section:
    sec = Section(
        "who",
        "Who or what is it",
        "Transfers that don't say who: choose the person, or a category such as Salary.",
    )
    rows = sorted(rows, key=_at_stake)
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
                    "rule_ok": rule_ok(classify.merchant_key(t.description_raw)),
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
        "Money that moved between accounts, but the other side isn't in the app. Say what it "
        "was (the house, a loan, a person), or that the other side is an account the app "
        "doesn't follow. If its statement is still to come, leave it: it pairs up on its own.",
    )
    kinds = {a.account_id: a.kind for a in db.scalars(select(Account))}
    since = sources.statements_from(db)
    # Workbook months count the workbook's rows, not these lines: nothing to ask about them.
    rows = [t for t in transfers.unmatched(db) if since is None or t.cash_month >= since]
    rows.sort(key=_at_stake)
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
                data={
                    "transaction_id": t.transaction_id,
                    "merchant_key": classify.merchant_key(t.description_raw),
                    "rule_ok": rule_ok(classify.merchant_key(t.description_raw)),
                    "statement_file_id": t.statement_file_id,
                    "account_kind": kinds.get(t.account_id or 0),
                    "category_id": t.category_id,
                },
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
        "Values on Net worth that haven't been updated for a while. Enter today's value, or "
        "stop counting it if you don't have it any more (or it's the same money as another "
        "item).",
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
                link="/debt/manage?stale=1",
                data={
                    "holding_id": i.holding_id,
                    "account_id": i.account_id,
                    "twin": twin,
                    "source": i.source,
                },
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
        "Patterns the app noticed. A rule categorizes future lines on its own; a bill is "
        "expected every month. Save it, change it, or say no.",
    )
    cats = {c.category_id: c for c in db.scalars(select(Category))}
    for s in rules_suggest.suggestions(db):
        c = cats.get(s.category_id)
        sec.tasks.append(
            Task(
                key=f"rule:{s.pattern}",
                kind="rule",
                title=f"Lines with “{s.pattern}” → {c.name if c else '?'}",
                detail=f"You chose {c.name if c else 'it'} for these {s.times} times; "
                "a rule does it on its own from now on",
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
                detail=("every month" if b.every_months == 1 else f"every {b.every_months} months")
                + f", around day {b.due_day} · seen {b.times} times",
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
        "Electronic invoices (SRI) that reach your email count for the yearly personal "
        "expenses deduction once they say whose they are and what they were for.",
    )
    g = gastos.summary(db, today.year)
    n = sum(x.to_classify for x in g.people) + g.unassigned
    if n:
        sec.tasks.append(
            Task(
                key=f"invoices:{today.year}",
                kind="invoices",
                title=f"{n} invoice{'' if n == 1 else 's'} without a person or a category "
                f"in {today.year}",
                link="/taxes",
            )
        )
    sec.count = n
    return sec


PURPOSE_DAYS = 120


def _purpose(db: Session, today: date, accounts: dict[int, str]) -> Section:
    """Lines on a card kept for one purpose that don't look like it (ADR-074): Juliana's school
    card bought something other than school, bus, food or insurance."""
    rows = line_context.unusual_lines(db, today - timedelta(days=PURPOSE_DAYS))
    who = sorted({w for _, w in rows if w})
    sec = Section(
        "purpose",
        f"Check: unusual on {' and '.join(who)}'s card" if who else "Check: unusual card lines",
        "A card kept for one purpose was used for something else. Check it: if it belongs, say so "
        "and it won't be asked again; if not, give it its category.",
    )
    gone = _dismissed(db)
    rows = [(t, w) for t, w in rows if _dismiss_key(f"purpose:{t.transaction_id}") not in gone]
    sec.count = len(rows)
    for t, w in rows[:MAX_TASKS]:
        sec.tasks.append(
            Task(
                key=f"purpose:{t.transaction_id}",
                kind="purpose",
                title=t.description_raw,
                detail=f"{t.txn_date:%b %d} · {_name(t, accounts)} · {w}'s card".strip(" ·"),
                amount=t.amount,
                on=t.txn_date,
                link=f"/transactions?q={t.transaction_id}",
                data={
                    "transaction_id": t.transaction_id,
                    "category_id": t.category_id,
                    "statement_file_id": t.statement_file_id,
                    "for": w,
                },
            )
        )
    return sec


def build(db: Session, today: date | None = None) -> Todo:
    """Everything that needs a decision, by section, ordered by the money at stake."""
    today = today or date.today()
    accounts = {a.account_id: a.name for a in db.scalars(select(Account))}
    unnamed = inbox.who_lines(db, today=today)
    who = _who(unnamed, accounts)
    asked = {t.transaction_id for t in unnamed}
    sections = [
        _categorize(db, accounts, asked),
        _purpose(db, today, accounts),
        who,
        _books(db, today),
        _loans(db, today),
        _transfers(db, accounts),
        _values(db, today),
        _suggestions(db, today),
        _invoices(db, today),
    ]
    gone = _dismissed(db)
    for sec in sections:
        kept = [t for t in sec.tasks if _dismiss_key(t.key) not in gone]
        sec.count -= len(sec.tasks) - len(kept)
        sec.tasks = kept
    return Todo(today, [s for s in sections if s.count])
