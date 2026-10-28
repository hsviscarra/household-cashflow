"""Monthly report (F16, ADR-015): one month's facts and 3 to 5 findings written from them.

The facts are worked out here, from the same services the pages use:
- cash flow (spending view): income, spending, savings, debt payments, net and savings rate,
  against last month and the average of the three months before;
- spending by group: the biggest moves against last month, the top categories and merchants;
- subscriptions: what they cost a month, and the ones that started or stopped;
- interest and fees paid in the month;
- net worth at the month's end against the month before, and each loan read from its
  amortization table;
- spending alerts (groups more than 30% above their average);
- for the current or last month, the projection's lowest cash and the payday after it;
- whether the month is complete (Data Status).

Findings are written by Claude from those facts (no account numbers, people's names or statement
text leave the server: totals, category and merchant names only), or by rules when Claude is off
or can't be reached. The report is saved; regenerating replaces it.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MonthlyReport, v_debt_cost, v_monthly_cashflow
from app.services import networth, projections, spending, status, subscriptions, suggest
from app.services.recurring import add_months, first

log = logging.getLogger(__name__)

ZERO = Decimal(0)
CENT = Decimal("0.01")
MIN_FINDINGS, MAX_FINDINGS = 3, 5
MAX_TOKENS = 16000
EFFORT: Final = "medium"
TONES = ("good", "bad", "neutral")
MINUS = "\u2212"  # the page's minus sign
CASHFLOW = ("income", "expenses", "savings", "debt_payments", "net")

SYSTEM = (
    "You write the monthly cash-flow report for a family in Quito, Ecuador (USD; the country is "
    "dollarized), for the parents to read in a minute. You get the month's facts as JSON, already "
    "computed. Write between 3 and 5 findings, most important first: what changed, why it "
    "matters, and what to do when there is something to do. Each finding has a title of at most "
    "8 words, a text of at most 45 words that quotes the numbers it relies on exactly as given "
    "(amounts with two decimals), and a tone: good, bad or neutral. Use only the facts given; "
    "never invent numbers, causes or merchants. If the month is incomplete, say so in one "
    "finding, and don't read drops against last month as savings: they are usually statements "
    "not loaded yet. Net worth's change compares only items valued at both dates; items first "
    "valued this month are listed apart and are not a gain. Write in English."
)
# Lines waiting for a category, not a kind of spending: Data Status counts them already.
NOT_A_GROUP = {"Uncategorized"}


class ReportError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _s(v: Decimal | None) -> str | None:
    return None if v is None else str(v.quantize(CENT))


def _d(v: object) -> Decimal:
    return Decimal(str(v)) if v is not None else ZERO


def _money(v: str | Decimal | None) -> str:
    """1,234.50, and negatives with the page's minus sign."""
    d = Decimal(str(v or 0))
    return f"{MINUS if d < 0 else ''}{abs(d):,.2f}"


def _day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def _month_end(month: date) -> date:
    return add_months(month, 1) - timedelta(days=1)


def months(db: Session) -> list[date]:
    """Months that can have a report: every month with cash flow, newest first."""
    return sorted(db.scalars(select(v_monthly_cashflow.c.cash_month)), reverse=True)


# ---------------------------------------------------------------- facts
def _cashflow(db: Session, month: date) -> dict[str, Any]:
    rows = {
        r.cash_month: r
        for r in db.execute(
            select(v_monthly_cashflow).where(
                v_monthly_cashflow.c.cash_month >= add_months(month, -3),
                v_monthly_cashflow.c.cash_month <= month,
            )
        )
    }

    def pick(m: date) -> dict[str, Decimal] | None:
        r = rows.get(m)
        return {k: _d(getattr(r, k)) for k in CASHFLOW} if r is not None else None

    now, prev = pick(month), pick(add_months(month, -1))
    before = [p for p in (pick(add_months(month, -i)) for i in (1, 2, 3)) if p]
    avg = {k: sum((b[k] for b in before), ZERO) / len(before) for k in CASHFLOW} if before else None

    def out(d: dict[str, Decimal] | None) -> dict[str, str | None] | None:
        if d is None:
            return None
        rate = (d["net"] / d["income"]).quantize(Decimal("0.0001")) if d["income"] else None
        return {
            **{k: _s(d[k]) for k in CASHFLOW},
            "savings_rate": None if rate is None else str(rate),
        }

    return {"month": out(now), "last_month": out(prev), "average_3_months": out(avg)}


def _spending(db: Session, month: date) -> dict[str, Any]:
    s = spending.analyze(db, month)
    movers = sorted(
        (g for g in s.groups if (g.amount or g.prev) and g.name not in NOT_A_GROUP),
        key=lambda g: (-abs(g.amount - g.prev), g.name),
    )[:3]
    cats = sorted(
        ((g.name, c) for g in s.groups for c in g.categories if c.amount > 0),
        key=lambda gc: (-gc[1].amount, gc[1].name),
    )[:5]
    return {
        "source": s.source,
        "total": _s(s.total.amount),
        "last_month": _s(s.total.prev),
        "same_month_last_year": _s(s.total.last_year),
        "biggest_moves": [
            {
                "group": g.name,
                "amount": _s(g.amount),
                "last_month": _s(g.prev),
                "change": _s(g.amount - g.prev),
            }
            for g in movers
        ],
        "top_categories": [
            {"group": gname, "category": c.name, "amount": _s(c.amount)} for gname, c in cats
        ],
        "top_merchants": [
            {"merchant": m.merchant, "group": m.group_name, "amount": _s(m.amount)}
            for m in s.merchants[:5]
        ],
    }


def _subscriptions(db: Session, month: date) -> dict[str, Any]:
    end = _month_end(month)
    found = [s for s in subscriptions.find(db, end) if s.cadence != "possible"]
    active = [s for s in found if s.active]

    def started(s: subscriptions.Subscription) -> bool:
        return bool(s.charges) and min(c.txn_date for c in s.charges) >= month

    def stopped(s: subscriptions.Subscription) -> bool:
        last = max((c.txn_date for c in s.charges), default=None)
        return not s.active and last is not None and last >= add_months(month, -3)

    def brief(s: subscriptions.Subscription) -> dict[str, Any]:
        return {"merchant": s.merchant, "cadence": s.cadence, "monthly_cost": _s(s.monthly_cost)}

    return {
        "active": len(active),
        "monthly_cost": _s(sum((s.monthly_cost for s in active), ZERO)),
        "started": [brief(s) for s in active if started(s)],
        "stopped": [brief(s) for s in found if stopped(s)],
    }


def _debt_cost(db: Session, month: date) -> dict[str, Any]:
    v = v_debt_cost
    by = {
        (kind, m): _d(total)
        for kind, m, total in db.execute(
            select(v.c.kind, v.c.cash_month, func.sum(v.c.amount))
            .where(v.c.cash_month >= date(month.year, 1, 1), v.c.cash_month <= month)
            .group_by(v.c.kind, v.c.cash_month)
        )
    }
    month_total = {
        k: sum((a for (kk, m), a in by.items() if kk == k and m == month), ZERO)
        for k in ("interest", "fee")
    }
    ytd = {k: sum((a for (kk, _), a in by.items() if kk == k), ZERO) for k in ("interest", "fee")}
    return {
        "interest": _s(month_total["interest"]),
        "fees": _s(month_total["fee"]),
        "interest_year_to_date": _s(ytd["interest"]),
        "fees_year_to_date": _s(ytd["fee"]),
    }


def _values(db: Session, day: date) -> dict[str, networth.Item]:
    return {
        i.key: i
        for i in networth.accounts(db, day) + networth.holdings(db, day)
        # A purchase reports 0 paid before its first value: that isn't a value yet.
        if i.is_active and i.value is not None and i.as_of is not None
    }


def _networth(db: Session, month: date, today: date) -> dict[str, Any]:
    """Net worth at the month's end. Its change compares like with like: only items valued at
    both month ends; an item first valued this month (a house entered today) is listed apart,
    not counted as a gain."""
    as_of = min(_month_end(month), today)
    sheet = networth.sheet(db, as_of, months=1)
    now = sheet.series[-1]
    now_items, before_items = _values(db, as_of), _values(db, month - timedelta(days=1))

    def signed(i: networth.Item) -> Decimal:
        return (i.value or ZERO) * (1 if i.side == "asset" else -1)

    both = set(now_items) & set(before_items)
    change = sum((signed(now_items[k]) - signed(before_items[k]) for k in both), ZERO)
    new = [
        {"name": now_items[k].name, "side": now_items[k].side, "value": _s(now_items[k].value)}
        for k in sorted(set(now_items) - set(before_items))
    ]
    loans = []
    for i in sheet.items:
        sched = i.loan.schedule if i.loan else None
        if i.holding_class != "loan" or not i.is_active or sched is None:
            continue
        loans.append(
            {
                "name": i.name,
                "balance": _s(i.value),
                "installments_left": sched.left,
                "next_installment": _s(sched.next_total),
                "paid_off": sched.payoff.isoformat()[:7] if sched.payoff else None,
                "interest_this_year": _s(sched.interest_this_year),
            }
        )
    return {
        "as_of": as_of.isoformat(),
        "assets": _s(now.assets),
        "liabilities": _s(now.liabilities),
        "net_worth": _s(now.net),
        "change": _s(change) if both else None,
        "first_valued_this_month": new,
        "loans": loans,
    }


def _outlook(db: Session, month: date, today: date) -> dict[str, Any] | None:
    """The projection only says something about the month just ended or the current one."""
    if month < add_months(first(today), -1):
        return None
    p = projections.project(db, today)
    return {
        "from": today.isoformat(),
        "lowest_cash": _s(p.lowest[1]) if p.lowest else None,
        "lowest_on": p.lowest[0].isoformat() if p.lowest else None,
        "next_payday": p.next_payday.day.isoformat() if p.next_payday else None,
        "next_3_months_net": _s(sum((m.net for m in p.months), ZERO)),
    }


def _status(db: Session, month: date, today: date) -> dict[str, Any]:
    st = next((m for m in status.month_status(db, today).months if m.month == month), None)
    if st is None:
        return {"complete": month <= today, "open": []}
    return {"complete": not st.items, "source": st.source, "open": [i.text for i in st.items]}


def facts(db: Session, month: date, today: date) -> dict[str, Any]:
    month = first(month)
    return {
        "month": month.isoformat()[:7],
        "data": _status(db, month, today),
        "cash_flow": _cashflow(db, month),
        "spending": _spending(db, month),
        "subscriptions": _subscriptions(db, month),
        "interest_and_fees": _debt_cost(db, month),
        "net_worth": _networth(db, month, today),
        "alerts": [
            {
                "group": a.group_name,
                "amount": _s(a.amount),
                "average": _s(a.average),
                "change": None if a.change is None else str(a.change),
            }
            for a in projections.alerts(db, add_months(month, 1))
            if a.group_name not in NOT_A_GROUP
        ],
        "outlook": _outlook(db, month, today),
    }


def for_claude(f: dict[str, Any]) -> dict[str, Any]:
    """What Claude sees: the facts without Data Status' texts (they name accounts, and so
    people), only how many things are open."""
    data = dict(f["data"])
    data["open_items"] = len(data.pop("open", []))
    return {**f, "data": data}


# ---------------------------------------------------------------- findings
@dataclass
class Finding:
    title: str
    text: str
    tone: str


def _upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def _pct(v: Decimal) -> str:
    return f"{MINUS if v < 0 else ''}{abs(v * 100):.0f}%"


def _above(change: Decimal) -> str:
    """0.35 -> "35% above"; 2.5 -> "3.5 times" (its average): big jumps read as multiples."""
    if change >= 1:
        times = change + 1
        return f"{times:.0f} times" if times >= 10 else f"{times:.1f} times"
    return f"{_pct(change)} above"


def rule_findings(f: dict[str, Any]) -> list[Finding]:
    """Findings written from the facts by fixed rules, most important first."""
    out: list[Finding] = []
    label = date.fromisoformat(f["month"] + "-01").strftime("%B")
    data = f["data"]
    if not data.get("complete", True):
        n = len(data.get("open", []))
        out.append(
            Finding(
                f"{label} isn't complete yet",
                f"{n} {'thing is' if n == 1 else 'things are'} still open in Data Status "
                "(missing statements, imports or uncategorized lines), so these numbers may "
                "change.",
                "neutral",
            )
        )
    cf = f["cash_flow"]
    now, avg = cf["month"], cf["average_3_months"]
    if now:
        net = Decimal(now["net"])
        text = (
            f"Income {_money(now['income'])}, spending {_money(now['expenses'])}, savings and "
            f"debt payments {_money(Decimal(now['savings']) + Decimal(now['debt_payments']))}: "
            f"net {'+' if net >= 0 else MINUS}{_money(abs(net))}"
        )
        if now["savings_rate"] is not None:
            text += f" ({_pct(Decimal(now['savings_rate']))} of income)"
        if avg:
            text += f", against a {_money(avg['net'])} average over the three months before"
        out.append(
            Finding(
                f"Net {'+' if net >= 0 else MINUS}{_money(abs(net))} in {label}",
                text + ".",
                "good" if net >= 0 else "bad",
            )
        )
    moves = f["spending"]["biggest_moves"]
    # In an incomplete month a drop is mostly statements not loaded yet: no "biggest change".
    if moves and Decimal(moves[0]["change"]) != 0 and data.get("complete", True):
        m = moves[0]
        change = Decimal(m["change"])
        out.append(
            Finding(
                f"{m['group']} {'up' if change > 0 else 'down'} {_money(abs(change))}",
                f"{m['group']} was {_money(m['amount'])} against {_money(m['last_month'])} last "
                "month, the biggest change of any group.",
                "bad" if change > 0 else "good",
            )
        )
    for a in f["alerts"][:1]:
        above = f" ({_above(Decimal(a['change']))})" if a["change"] else ""
        out.append(
            Finding(
                f"{a['group']} above its usual",
                f"{a['group']} spent {_money(a['amount'])} against a {_money(a['average'])} "
                f"average{above}.",
                "bad",
            )
        )
    outlook = f.get("outlook")
    if outlook and outlook["lowest_cash"] is not None and Decimal(outlook["lowest_cash"]) < 0:
        payday = (
            f", before the next payday on {_day(outlook['next_payday'])}"
            if outlook["next_payday"]
            else ", and no income is projected after it"
        )
        out.append(
            Finding(
                "Cash runs short ahead",
                f"The projection reaches {_money(outlook['lowest_cash'])} on "
                f"{_day(outlook['lowest_on'])}{payday}. Move money in before then or delay a "
                "payment.",
                "bad",
            )
        )
    debt = f["interest_and_fees"]
    paid = Decimal(debt["interest"]) + Decimal(debt["fees"])
    year = Decimal(debt["interest_year_to_date"]) + Decimal(debt["fees_year_to_date"])
    if paid > 0:
        out.append(
            Finding(
                f"{_money(paid)} in interest and fees",
                f"Interest {_money(debt['interest'])} and fees {_money(debt['fees'])} this month; "
                f"{_money(year)} so far this year.",
                "bad",
            )
        )
    subs = f["subscriptions"]
    if subs["started"] or subs["stopped"]:
        parts = []
        if subs["started"]:
            parts.append("started: " + ", ".join(s["merchant"] for s in subs["started"]))
        if subs["stopped"]:
            parts.append("stopped: " + ", ".join(s["merchant"] for s in subs["stopped"]))
        out.append(
            Finding(
                "Subscriptions changed",
                f"{_upper_first('; '.join(parts))}. {subs['active']} active subscriptions cost "
                f"{_money(subs['monthly_cost'])} a month.",
                "neutral",
            )
        )
    nw = f["net_worth"]
    if nw["change"] is not None:
        change = Decimal(nw["change"])
        out.append(
            Finding(
                f"Net worth {'up' if change >= 0 else 'down'} {_money(abs(change))}",
                f"Net worth {_money(nw['net_worth'])} on {_day(nw['as_of'])}: owned "
                f"{_money(nw['assets'])}, owed {_money(nw['liabilities'])}"
                + (
                    "; first valued this month: "
                    + ", ".join(n["name"] for n in nw.get("first_valued_this_month", []))
                    + " (not counted as a change)."
                    if nw.get("first_valued_this_month")
                    else "."
                ),
                "good" if change >= 0 else "bad",
            )
        )
    if len(out) < MIN_FINDINGS and subs["active"]:
        out.append(
            Finding(
                f"{subs['active']} subscriptions",
                f"Active subscriptions cost {_money(subs['monthly_cost'])} a month.",
                "neutral",
            )
        )
    return out[:MAX_FINDINGS]


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                        "tone": {"type": "string", "enum": list(TONES)},
                    },
                    "required": ["title", "text", "tone"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    }


def parse_findings(text: str) -> list[Finding]:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON in the reply")
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("no findings list")
    out = [
        Finding(
            str(i["title"]).strip()[:120],
            str(i["text"]).strip()[:600],
            i["tone"] if i.get("tone") in TONES else "neutral",
        )
        for i in items
        if isinstance(i, dict) and i.get("title") and i.get("text")
    ]
    if len(out) < MIN_FINDINGS:
        raise ValueError(f"{len(out)} findings")
    return out[:MAX_FINDINGS]


def call_claude(f: dict[str, Any]) -> list[Finding]:
    """One Messages API call with a JSON-schema answer. Replaced in tests."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=120)
    try:
        response = client.messages.create(
            model=settings.anthropic_report_model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(for_claude(f), ensure_ascii=False)}],
            output_config={
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": _schema()},
            },
        )
    except anthropic.APIError as exc:
        raise ReportError(f"Claude could not be reached: {exc.__class__.__name__}.", 502) from exc
    if getattr(response, "stop_reason", None) in ("max_tokens", "refusal"):
        raise ReportError(f"Claude didn't finish the findings ({response.stop_reason}).", 502)
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        return parse_findings(text)
    except (ValueError, KeyError) as exc:
        log.warning("Report findings unreadable: %s, %s characters", exc, len(text))
        raise ReportError("Claude's findings could not be read.", 502) from exc


# ---------------------------------------------------------------- saved reports
@dataclass
class Report:
    month: date
    written_by: str
    model: str | None
    generated_at: datetime | None
    generated_by: str
    facts: dict[str, Any]
    findings: list[Finding]
    notice: str | None = None


def _load(r: MonthlyReport) -> Report:
    return Report(
        r.month,
        r.written_by,
        r.model,
        r.generated_at,
        r.generated_by,
        json.loads(r.facts_json),
        [Finding(**x) for x in json.loads(r.findings_json)],
    )


def get(db: Session, month: date) -> Report | None:
    r = db.scalar(select(MonthlyReport).where(MonthlyReport.month == first(month)))
    return _load(r) if r is not None else None


def generate(db: Session, month: date, user: str, today: date | None = None) -> Report:
    """Work out the facts, write the findings (Claude when it is on, else rules; rules when
    Claude fails, with a notice) and save the report, replacing the month's earlier one."""
    today = today or date.today()
    month = first(month)
    if month > first(today):
        raise ReportError("That month hasn't started yet.")
    f = facts(db, month, today)
    if f["cash_flow"]["month"] is None:
        raise ReportError(f"Nothing is loaded for {month:%B %Y} yet.")
    notice = None
    written_by, model = "rules", None
    if suggest.available():
        try:
            found = call_claude(f)
            written_by, model = "claude", get_settings().anthropic_report_model
        except ReportError as exc:
            notice = f"{exc} These findings are written by rules instead."
            found = rule_findings(f)
    else:
        found = rule_findings(f)
    r = db.scalar(select(MonthlyReport).where(MonthlyReport.month == month))
    if r is None:
        r = MonthlyReport(month=month)
        db.add(r)
    r.written_by, r.model, r.generated_by = written_by, model, user
    r.facts_json = json.dumps(f, ensure_ascii=False)
    r.findings_json = json.dumps([x.__dict__ for x in found], ensure_ascii=False)
    r.generated_at = datetime.now()
    db.commit()
    db.refresh(r)
    out = _load(r)
    out.notice = notice
    return out
