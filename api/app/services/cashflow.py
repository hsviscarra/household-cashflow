"""One month's money in and out, by category, for the Cash flow page (ADR-027): the Sankey, the
"why it changed" waterfall and the drill-down to lines. The same lines count as on
mart.v_category_month (workbook months keep the workbook, statement months the statements, a split
line through its parts, transfers left out), plus the Both/Hernan/Lauren switch (ADR-026)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, case, exists, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import FROM_BANKS, Account, Category, Transaction, v_excel_month
from app.services.recurring import add_months, first

ZERO = Decimal("0")
TREND_MONTHS = 12
LINE_LIMIT = 500

Group = aliased(Category)
Part = aliased(Transaction)


def counted[S: Select[*tuple[Any, ...]]](q: S, person: str | None = None) -> S:
    """Only the lines that count in the cash flow, and only one person's when asked."""
    t = Transaction
    excel = select(v_excel_month.c.cash_month)
    q = q.where(
        t.type != "transfer",
        not_(and_(t.source.in_(FROM_BANKS), t.cash_month.in_(excel))),
        not_(and_(t.source == "excel_history", t.cash_month.not_in(excel))),
        ~exists(select(Part.transaction_id).where(Part.parent_transaction_id == t.transaction_id)),
    )
    if person == "Joint":
        q = q.where(or_(t.person == "Joint", t.person.is_(None)))
    elif person:
        q = q.where(t.person == person)
    return q


def _signed() -> Any:
    """Money in positive, money out positive: like mart.v_category_month."""
    t = Transaction
    return case((t.type == "income", t.amount), else_=-t.amount)


@dataclass
class Flow:
    type: str
    group_id: int
    group_name: str
    group_color: str | None
    category_id: int
    category_name: str
    amount: Decimal
    prev: Decimal
    transactions: int


@dataclass
class MonthTotal:
    month: date
    money_in: Decimal
    money_out: Decimal


@dataclass
class Flows:
    month: date
    prev_month: date
    months: list[date]
    source: str  # "excel" | "statements" | "none"
    flows: list[Flow]
    trend: list[MonthTotal]


def _months(db: Session, person: str | None) -> list[date]:
    q = counted(select(Transaction.cash_month).distinct(), person)
    return sorted(db.scalars(q), reverse=True)


def _by_category(db: Session, month: date, person: str | None) -> dict[tuple[Any, ...], Any]:
    """Per (type, group, category): names, color, amount and lines. Grouped on plain columns and
    named in Python, since SQL Server can't match parameters in GROUP BY to the select list."""
    t = Transaction
    cols = (
        t.type,
        Group.category_id,
        Group.name,
        Group.color,
        Category.category_id,
        Category.name,
        Category.color,
    )
    q = counted(
        select(*cols, func.sum(_signed()), func.count())
        .outerjoin(Category, Category.category_id == t.category_id)
        .outerjoin(Group, Group.category_id == Category.parent_id)
        .where(t.cash_month == month)
        .group_by(*cols),
        person,
    )
    out: dict[tuple[Any, ...], Any] = {}
    for typ, gid, gname, gcolor, cid, cname, ccolor, total, n in db.execute(q):
        key = (typ, int(gid if gid is not None else cid or 0), int(cid or 0))
        name = gname or cname or "Uncategorized"
        found = out.get(key)
        amount = Decimal(str(total)) + (found[3] if found else ZERO)
        out[key] = (
            name,
            gcolor or ccolor,
            cname or "Uncategorized",
            amount,
            int(n) + (found[4] if found else 0),
        )
    return out


def trend(
    db: Session, month: date, person: str | None, count: int = TREND_MONTHS
) -> list[MonthTotal]:
    t = Transaction
    start = add_months(month, -(count - 1))
    q = counted(
        select(
            t.cash_month,
            func.sum(case((t.type == "income", t.amount), else_=0)),
            func.sum(case((t.type != "income", -t.amount), else_=0)),
        )
        .where(t.cash_month >= start, t.cash_month <= month)
        .group_by(t.cash_month),
        person,
    )
    found = {m: (Decimal(str(i)), Decimal(str(o))) for m, i, o in db.execute(q)}
    out = []
    for i in range(count):
        m = add_months(start, i)
        money_in, money_out = found.get(m, (ZERO, ZERO))
        out.append(MonthTotal(m, money_in, money_out))
    return out


def flows(db: Session, month: date | None = None, person: str | None = None) -> Flows:
    months = _months(db, person)
    month = first(month) if month else (months[0] if months else first(date.today()))
    prev_month = add_months(month, -1)
    now, prev = _by_category(db, month, person), _by_category(db, prev_month, person)
    out: list[Flow] = []
    for key in set(now) | set(prev):
        info = now.get(key) or prev[key]
        out.append(
            Flow(
                type=key[0],
                group_id=key[1],
                group_name=info[0],
                group_color=info[1],
                category_id=key[2],
                category_name=info[2],
                amount=now[key][3] if key in now else ZERO,
                prev=prev[key][3] if key in prev else ZERO,
                transactions=now[key][4] if key in now else 0,
            )
        )
    out.sort(key=lambda f: (-f.amount, f.category_name))
    sources = set(
        db.scalars(
            counted(select(Transaction.source).where(Transaction.cash_month == month).distinct())
        )
    )
    source = "excel" if "excel_history" in sources else "statements" if sources else "none"
    return Flows(month, prev_month, months, source, out, trend(db, month, person))


@dataclass
class Line:
    transaction_id: int
    txn_date: date
    description: str
    merchant: str | None
    amount: Decimal
    type: str
    category_name: str | None
    account_name: str | None
    person: str | None
    source: str
    notes: str | None


def lines(
    db: Session,
    month: date,
    *,
    side: str | None = None,
    group_id: int | None = None,
    category_id: int | None = None,
    merchant: str | None = None,
    person: str | None = None,
) -> list[Line]:
    """The lines behind one band or row: money in or out, a group (0: no category), a category,
    a merchant. Amounts keep their sign (negative = money out)."""
    t = Transaction
    q = (
        select(t, Category.name, Account.name)
        .outerjoin(Category, Category.category_id == t.category_id)
        .outerjoin(Account, Account.account_id == t.account_id)
        .where(t.cash_month == first(month))
        .order_by(t.txn_date, t.transaction_id)
        .limit(LINE_LIMIT)
    )
    if side == "in":
        q = q.where(t.type == "income")
    elif side == "out":
        q = q.where(t.type != "income")
    if category_id is not None:
        q = (
            q.where(t.category_id == category_id)
            if category_id
            else q.where(t.category_id.is_(None))
        )
    if group_id is not None:
        if group_id == 0:
            q = q.where(t.category_id.is_(None))
        else:
            q = q.where(or_(Category.parent_id == group_id, Category.category_id == group_id))
    if merchant:
        q = q.where(func.coalesce(t.merchant, t.description_raw) == merchant)
    found = db.execute(counted(q, person))
    return [
        Line(
            transaction_id=r.transaction_id,
            txn_date=r.txn_date,
            description=r.description_raw,
            merchant=r.merchant,
            amount=r.amount,
            type=r.type,
            category_name=cname,
            account_name=aname,
            person=r.person,
            source=r.source,
            notes=r.notes,
        )
        for r, cname, aname in found
    ]
