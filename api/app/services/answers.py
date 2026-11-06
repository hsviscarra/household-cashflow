"""The month in ten answers (ADR-033): the questions a household asks at month end, answered
live from the same services the pages use. Each answer is short (the number), with one sentence
of detail and a link to the page that shows it. Nothing here is saved or sent anywhere."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services import classify, networth, people, projections, recurring, report, shopping
from app.services import spending as spending_service
from app.services.recurring import add_months, first

ZERO = Decimal(0)
MINUS = "\u2212"  # the page's minus sign


@dataclass
class Answer:
    n: int
    question: str
    answer: str
    detail: str
    tone: str  # good, warn, neutral
    link: str | None = None


def _money(v: Decimal | str | None) -> str:
    d = Decimal(str(v or 0))
    return f"{MINUS if d < 0 else ''}${abs(d):,.2f}"


def _pct(now: Decimal, before: Decimal) -> str | None:
    if not before:
        return None
    change = (now - before) / before * 100
    return f"{'+' if change >= 0 else MINUS}{abs(change):.0f}%"


def _mon(m: date) -> str:
    return m.strftime("%b")


def _spent(db: Session, month: date) -> Answer:
    s = spending_service.analyze(db, month)
    cf = report._cashflow(db, month)
    avg = cf["average_3_months"]
    usual = Decimal(avg["expenses"]) if avg and avg["expenses"] else None
    now, prev = s.total.amount, s.total.prev
    vs = _pct(now, prev)
    detail = f"Spent {_money(now)}: {_money(prev)} in {_mon(add_months(month, -1))}"
    if usual is not None:
        detail += f", about {_money(usual)} a month over the three months before"
    return Answer(
        1,
        "Did we spend more or less than usual?",
        f"{vs} vs {_mon(add_months(month, -1))}" if vs else _money(now),
        detail + ".",
        "good" if prev and now <= prev else "warn" if prev else "neutral",
        f"/cashflow?month={month:%Y-%m}",
    )


def _unusual(db: Session, month: date, ideas: list[shopping.Idea]) -> Answer:
    odd = [i for i in ideas if i.key.startswith(("new:", "rising:"))]
    alerts = [
        a
        for a in projections.alerts(db, add_months(month, 1))
        if not any(i.key == f"rising:{a.group_id}" for i in odd)
    ]
    items = [i.title for i in odd] + [
        f"{a.group_name} {_money(a.amount)} against {_money(a.average)} usually" for a in alerts
    ]
    n = len(items)
    return Answer(
        2,
        "What was unusual?",
        f"{n} {'thing' if n == 1 else 'things'}" if n else "Nothing",
        " · ".join(items[:3]) + ("." if items else "")
        if items
        else "No new merchants of $50 or more, and every group near its usual.",
        "neutral" if n else "good",
        f"/spending?month={month:%Y-%m}&view=merchants",
    )


def _bills(db: Session, month: date, today: date) -> Answer:
    bills = [
        b
        for b in recurring.bills(db, month, today)
        if b.type not in ("income", "refund") and b.status != "skipped"
    ]
    if not bills:
        return Answer(
            3,
            "Did every bill get paid?",
            "No bills set",
            "Add your bills on Bills & subscriptions to check them each month.",
            "neutral",
            "/recurring",
        )
    paid = [b for b in bills if b.status == "paid"]
    late = [b for b in bills if b.status == "late"]
    open_ = [b for b in bills if b.status != "paid"]
    detail = (
        "Every one matched a statement line."
        if not open_
        else "Not seen yet: "
        + ", ".join(
            f"{b.name}{f' ({b.account_name})' if b.account_name else ''}" for b in open_[:5]
        )
        + "."
    )
    return Answer(
        3,
        "Did every bill get paid?",
        f"{len(paid)} of {len(bills)}",
        detail,
        "good" if not open_ else "warn" if late else "neutral",
        f"/recurring?month={month:%Y-%m}",
    )


def _purchase(items: list[networth.Item]) -> Answer:
    goals = [i for i in items if i.is_active and i.purchase is not None]
    if not goals:
        return Answer(
            4,
            "Are we on track for the house?",
            "No purchase set",
            "Add the down payment on Net worth as a purchase in progress to follow it here.",
            "neutral",
            "/debt",
        )
    g = goals[0]
    p = g.purchase
    assert p is not None
    share = (p.paid / p.target * 100) if p.target else ZERO
    left = (
        f"; {p.installments_left} installments of {_money(p.installment)} left"
        if p.installments_left and p.installment
        else ""
    )
    return Answer(
        4,
        f"Are we on track for {g.name}?",
        f"{share:.0f}% paid",
        f"{_money(p.paid)} of the {_money(p.target)} down payment{left}.",
        "good",
        "/debt",
    )


def _cash(db: Session, month: date, today: date) -> Answer:
    if month < add_months(first(today), -1):
        return Answer(
            5,
            "Will cash be short next month?",
            "—",
            "The forecast looks ahead from today: open the latest month to see it.",
            "neutral",
            "/projections",
        )
    p = projections.project(db, today, horizon=1)
    short = [a for a in p.accounts if a.under_floor]
    low = p.lowest
    if p.first_short is None and not short:
        return Answer(
            5,
            "Will cash be short next month?",
            "No",
            f"Lowest total cash {_money(low[1])} on {low[0]:%b %d}." if low else "No bills ahead.",
            "good",
            "/projections",
        )
    a = short[0] if short else None
    detail = (
        f"{a.name} goes under {_money(p.floor)} on {a.under_floor:%b %d}: "
        f"move {_money(a.move)} in before then."
        if a and a.under_floor
        else f"Total cash dips to {_money(low[1])} on {low[0]:%b %d}."
        if low
        else ""
    )
    return Answer(5, "Will cash be short next month?", "Yes", detail, "warn", "/projections")


def _save(ideas: list[shopping.Idea]) -> Answer:
    top = [i for i in ideas if not i.key.startswith("rising:")][:3]
    if not top:
        return Answer(
            6,
            "Where could we save?",
            "Nothing stands out",
            "No fees, delivery or small repeated charges worth a look this month.",
            "good",
            "/spending",
        )
    total = sum((i.amount for i in top), ZERO)
    return Answer(
        6,
        "Where could we save?",
        f"up to {_money(total)}",
        " · ".join(f"{i.title} {_money(i.amount)}" for i in top) + ".",
        "neutral",
        top[0].link,
    )


def _cards(db: Session, month: date) -> Answer:
    d = report._debt_cost(db, month)
    interest, fees = Decimal(d["interest"] or 0), Decimal(d["fees"] or 0)
    total = interest + fees
    return Answer(
        7,
        "What did the cards and banks cost us?",
        _money(total),
        f"Interest {_money(interest)} and fees {_money(fees)} this month; "
        f"{_money(Decimal(d['interest_year_to_date'] or 0) + Decimal(d['fees_year_to_date'] or 0))}"
        " so far this year.",
        "good" if not total else "neutral",
        "/debt",
    )


def _held(db: Session, items: list[networth.Item]) -> Answer:
    linked = people.linked_holdings(db)
    held = [i for i in items if i.is_active and i.holding_id in linked and i.side == "liability"]
    total = sum((i.value or ZERO for i in held), ZERO)
    return Answer(
        8,
        "How much is someone else's money?",
        _money(total),
        (
            " · ".join(f"{i.name} {_money(i.value)}" for i in held)
            + ". Not counted as yours in the forecast."
        )
        if held
        else "Nobody's money is held in your accounts.",
        "neutral",
        "/people",
    )


def _networth(db: Session, month: date, today: date) -> Answer:
    n = report._networth(db, month, today)
    change = Decimal(n["change"]) if n["change"] is not None else None
    new = n["first_valued_this_month"]
    extra = f" {len(new)} item(s) first valued this month aren't counted as a gain." if new else ""
    if change is None:
        return Answer(
            9,
            "Did our net worth go up?",
            "—",
            "Not enough values at both month ends to compare." + extra,
            "neutral",
            "/debt",
        )
    return Answer(
        9,
        "Did our net worth go up?",
        f"{'+' if change >= 0 else MINUS}${abs(change):,.2f}",
        f"Net worth {_money(n['net_worth'])} on {n['as_of']}, comparing items valued at both "
        "month ends." + extra,
        "good" if change >= 0 else "warn",
        "/debt",
    )


def _trust(db: Session, month: date, today: date) -> Answer:
    st = report._status(db, month, today)
    uncategorized = len(classify.uncategorized(db, month))
    gaps = list(st["open"])
    if uncategorized:
        gaps.append(
            f"{uncategorized} {'line' if uncategorized == 1 else 'lines'} without a category"
        )
    return Answer(
        10,
        "Can I trust these numbers?",
        "Yes" if not gaps else f"{len(gaps)} {'gap' if len(gaps) == 1 else 'gaps'}",
        "Every statement is in and every line has a category."
        if not gaps
        else " · ".join(gaps[:4]) + ".",
        "good" if not gaps else "warn",
        "/status",
    )


def answers(db: Session, month: date, today: date | None = None) -> list[Answer]:
    today = today or date.today()
    month = first(month)
    ideas = shopping.ideas(db, month)
    items = networth.holdings(db, min(report._month_end(month), today))
    return [
        _spent(db, month),
        _unusual(db, month, ideas),
        _bills(db, month, today),
        _purchase(items),
        _cash(db, month, today),
        _save(ideas),
        _cards(db, month),
        _held(db, items),
        _networth(db, month, today),
        _trust(db, month, today),
    ]
