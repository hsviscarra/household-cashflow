"""Claude's MCP endpoint (F18, ADR-017): the household's analysis views as tools.

Served at /mcp by the app (streamable HTTP, stateless, JSON responses), behind a bearer token
(MCP_TOKEN, checked in app.auth). Every reading tool goes through the read-only `cashflow_reader`
login (app.db.reader). The one exception (F22, ADR-019) is save_portfolio: it writes the
Interactive Brokers value and positions Claude read through Hernan's IBKR connector, with the
app's own login, and nothing else; each save is in audit.load_log.
Months are "YYYY-MM"; amounts are USD strings with two decimals.
"""

from collections import defaultdict
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.routing import Route

from app.db import get_engine
from app.db.reader import get_reader_engine
from app.models import (
    v_category_month,
    v_debt_cost,
    v_monthly_cash,
    v_monthly_cashflow,
    v_spending_line,
)
from app.services import budget as budget_service
from app.services import (
    gastos,
    goals,
    groceries,
    ibkr,
    invoices,
    iva,
    networth,
    product_labels,
    watchdog,
)
from app.services import loans as loan_service
from app.services import recurring as recurring_service
from app.services import report as report_service
from app.services import status as status_service
from app.services.classify import merchant_key

CENT = Decimal("0.01")
ZERO = Decimal(0)
MAX_LINES = 500

INSTRUCTIONS = """\
Access to Hernan and Lauren's household cash flow (Quito, Ecuador; USD, the country is
dollarized). Months are YYYY-MM. Amounts are USD with two decimals.
- Cash flow (cash_flow, compare_months): income, expenses, savings, debt payments and net per
  month. The "spending" view counts card purchases when made; the "cash" view counts money in and
  out of the bank accounts, cards when paid. Transfers between own accounts are never counted.
- Spending (spending_by_category, spending_lines, top_merchants): expenses plus fees and interest,
  less refunds, as positive amounts, by group (e.g. Groceries) and category (e.g. Supermarket).
  "Uncategorized" means lines still waiting for a category, not a kind of spending.
- Months through June 2026 come from the Cash Flow workbook (category totals, no merchants);
  later months come from bank and card statements and may be incomplete until every statement is
  loaded, so a drop against an earlier month can be a statement not loaded yet.
- interest_and_fees: card interest and bank fees by account and month.
- balance_sheet, loans: what the household owns and owes (bank and card balances from
  statements; property, vehicles, investments and purchases entered on the app; loans from their
  amortization tables) and net worth by month. monthly_report: a month's saved findings.
- purchases: what was bought in a month, from electronic invoices (supermarket, pharmacy and
  other vendors), by product group and top products. Only invoices that reached the app count,
  so it's part of the month's spending, not all of it.
- save_portfolio is the only tool that writes: when Hernan asks to update his portfolio, read the
  Interactive Brokers connector (get_account_positions, get_account_summary) and save what it
  returned, unchanged. Everything else is read-only.
Quote the numbers you use; don't invent causes the data doesn't show.
"""

mcp = FastMCP(
    "household-cashflow",
    instructions=INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    # The bearer token protects the endpoint; the Host is Azure's, not localhost.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _m(text: str) -> date:
    try:
        y, m = text.strip()[:7].split("-")
        return date(int(y), int(m), 1)
    except ValueError as exc:
        raise ValueError(f"Months look like 2026-10, not {text!r}.") from exc


def _s(v: Any) -> str:
    return str(Decimal(str(v or 0)).quantize(CENT))


def _month(d: date) -> str:
    return d.isoformat()[:7]


def _rows(q: Any) -> list[Any]:
    with get_reader_engine().connect() as conn:
        return list(conn.execute(q))


FLOW = ("income", "expenses", "savings", "debt_payments", "net")


def _flow(row: Any, view: str) -> dict[str, Any]:
    out: dict[str, Any] = {"month": _month(row.cash_month)}
    out.update({k: _s(getattr(row, k)) for k in FLOW})
    if view == "cash":
        out["card_payments"] = _s(row.card_payments)
    out["savings_rate"] = None if row.savings_rate is None else str(row.savings_rate)
    out["transactions"] = int(row.transactions)
    return out


@mcp.tool()
def months() -> dict[str, Any]:
    """Which months have data: the first and last month, and how many."""
    v = v_monthly_cashflow
    found = [r.cash_month for r in _rows(select(v.c.cash_month).order_by(v.c.cash_month))]
    return {
        "first": _month(found[0]) if found else None,
        "last": _month(found[-1]) if found else None,
        "count": len(found),
    }


@mcp.tool()
def cash_flow(from_month: str, to_month: str, view: str = "spending") -> list[dict[str, Any]]:
    """Income, expenses, savings, debt payments, net and savings rate per month, from_month to
    to_month inclusive (YYYY-MM). view is "spending" (card purchases when made) or "cash" (money
    in and out of the bank accounts; card payments shown separately)."""
    if view not in ("spending", "cash"):
        raise ValueError('view is "spending" or "cash".')
    v = v_monthly_cash if view == "cash" else v_monthly_cashflow
    q = (
        select(v)
        .where(v.c.cash_month >= _m(from_month), v.c.cash_month <= _m(to_month))
        .order_by(v.c.cash_month)
    )
    return [_flow(r, view) for r in _rows(q)]


def _group_totals(month: date) -> dict[str, Decimal]:
    v = v_spending_line
    out: dict[str, Decimal] = {}
    for name, total in _rows(
        select(v.c.group_name, func.sum(v.c.amount))
        .where(v.c.cash_month == month)
        .group_by(v.c.group_name)
    ):
        out[name] = Decimal(str(total))
    return out


@mcp.tool()
def compare_months(month: str, other: str) -> dict[str, Any]:
    """Compare two months (YYYY-MM): cash flow side by side and each spending group's change,
    biggest change first. Use for questions like "how did October compare to September?"."""
    a, b = _m(month), _m(other)
    v = v_monthly_cashflow
    flows = {
        r.cash_month: _flow(r, "spending")
        for r in _rows(select(v).where(v.c.cash_month.in_([a, b])))
    }
    ga, gb = _group_totals(a), _group_totals(b)
    groups = [
        {
            "group": g,
            month: _s(ga.get(g, ZERO)),
            other: _s(gb.get(g, ZERO)),
            "change": _s(ga.get(g, ZERO) - gb.get(g, ZERO)),
        }
        for g in set(ga) | set(gb)
    ]
    groups.sort(key=lambda x: (-abs(Decimal(x["change"])), x["group"]))
    return {
        "months": [month, other],
        "cash_flow": {month: flows.get(a), other: flows.get(b)},
        "spending_total": {month: _s(sum(ga.values(), ZERO)), other: _s(sum(gb.values(), ZERO))},
        "groups": groups,
    }


@mcp.tool()
def spending_by_category(month: str) -> list[dict[str, Any]]:
    """Every group and category in a month (YYYY-MM) with its amount and line count, by type
    (income, expense, fee_interest, refund, savings, debt_payment). Amounts are positive."""
    v = v_category_month
    q = (
        select(v)
        .where(v.c.cash_month == _m(month))
        .order_by(v.c.type, v.c.amount.desc(), v.c.group_name, v.c.category_name)
    )
    return [
        {
            "type": r.type,
            "group": r.group_name,
            "category": r.category_name,
            "amount": _s(r.amount),
            "transactions": int(r.transactions),
        }
        for r in _rows(q)
    ]


@mcp.tool()
def spending_lines(
    month: str,
    group: str | None = None,
    category: str | None = None,
    merchant: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """The spending lines of a month (YYYY-MM), biggest first, optionally only one group or
    category (exact name) or merchants containing a text. At most 500 lines."""
    v = v_spending_line
    q = select(v).where(v.c.cash_month == _m(month))
    if group:
        q = q.where(v.c.group_name == group)
    if category:
        q = q.where(v.c.category_name == category)
    if merchant:
        q = q.where(v.c.merchant.ilike(f"%{merchant}%"))
    q = q.order_by(v.c.amount.desc(), v.c.txn_date).limit(max(1, min(limit, MAX_LINES)))
    return [
        {
            "date": r.txn_date.isoformat(),
            "amount": _s(r.amount),
            "group": r.group_name,
            "category": r.category_name,
            "merchant": r.merchant,
            "account": r.account_name,
            "person": r.person,
            "source": r.source,
        }
        for r in _rows(q)
    ]


@mcp.tool()
def month_lines(
    month: str, type: str | None = None, text: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Every line of a month (YYYY-MM) as the cash flow counts it, any type: income, expense,
    savings, debt_payment, transfer, refund, fee_interest. Optionally only one type, or only lines
    whose description holds a text (then also uncounted lines a month around). At most 500."""
    from app.services import cashflow

    with _session() as db:
        found = (
            cashflow.search(db, text, _m(month))
            if text
            else cashflow.lines(db, _m(month), type_=type or None)
        )
    if type and text:
        found = [ln for ln in found if ln.type == type]
    return [
        {
            "date": ln.txn_date.isoformat(),
            "amount": _s(ln.amount),
            "type": ln.type,
            "category": ln.category_name,
            "description": ln.description,
            "account": ln.account_name,
            "person": ln.person,
            "counterparty": ln.counterparty,
            "source": ln.source,
        }
        for ln in found[: max(1, min(limit, MAX_LINES))]
    ]


@mcp.tool()
def top_merchants(month: str, limit: int = 10) -> list[dict[str, Any]]:
    """The merchants with the most spending in a month (YYYY-MM), reference numbers removed so
    one merchant's lines add up. Months from the workbook have no merchants."""
    v = v_spending_line
    totals: dict[str, list[Any]] = defaultdict(lambda: [ZERO, 0, ""])
    for merchant, group, amount in _rows(
        select(v.c.merchant, v.c.group_name, v.c.amount).where(
            v.c.cash_month == _m(month), v.c.source != "excel_history"
        )
    ):
        key = merchant_key(str(merchant)) or str(merchant)
        t = totals[key]
        t[0] += Decimal(str(amount))
        t[1] += 1
        t[2] = t[2] or group
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return [
        {"merchant": k, "group": g, "amount": _s(a), "transactions": n}
        for k, (a, n, g) in ranked[: max(1, min(limit, 50))]
        if a > 0
    ]


@mcp.tool()
def interest_and_fees(year: int) -> dict[str, Any]:
    """Card interest and bank fees in a year, by account and month, with the year's totals."""
    v = v_debt_cost
    rows = _rows(
        select(v)
        .where(v.c.cash_month >= date(year, 1, 1), v.c.cash_month <= date(year, 12, 1))
        .order_by(v.c.cash_month, v.c.account_name)
    )
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        totals[r.kind] += Decimal(str(r.amount))
    return {
        "year": year,
        "interest": _s(totals["interest"]),
        "fees": _s(totals["fee"]),
        "lines": [
            {
                "month": _month(r.cash_month),
                "account": r.account_name or "Cash Flow sheet",
                "kind": r.kind,
                "category": r.category_name,
                "amount": _s(r.amount),
            }
            for r in rows
        ],
    }


def _session() -> Session:
    return Session(get_reader_engine())


def _item(i: networth.Item, positions: list[Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": i.name,
        "side": i.side,
        "kind": i.holding_class,
        "value": None if i.value is None else _s(i.value),
        "as_of": i.as_of.isoformat() if i.as_of else None,
        "source": i.source,
    }
    if i.purchase:
        p = i.purchase
        out["purchase"] = {
            "target": _s(p.target),
            "paid": _s(p.paid),
            "remaining": _s(p.remaining),
            "installment": None if p.installment is None else _s(p.installment),
            "installments_left": p.installments_left,
            "full_price": None if p.full_price is None else _s(p.full_price),
            "to_finance_at_delivery": None if p.at_delivery is None else _s(p.at_delivery),
        }
    if i.loan and i.loan.monthly_payment is not None:
        out["monthly_payment"] = _s(i.loan.monthly_payment)
    if positions:
        out["positions"] = [
            {
                "symbol": p.symbol,
                "description": p.description,
                "quantity": format(p.quantity.normalize(), "f"),
                "price": format(p.price.normalize(), "f"),
                "value": _s(p.value),
                "unrealized": None if p.unrealized is None else _s(p.unrealized),
            }
            for p in positions
        ]
    return out


@mcp.tool()
def balance_sheet(as_of: str | None = None) -> dict[str, Any]:
    """What the household owns and owes on a day (YYYY-MM-DD, default today): every asset and
    liability with its latest value and where it came from (a statement, a value entered on the
    page, the workbook, a loan's amortization table), totals, net worth, commitments still to
    pay on purchases in progress, and net worth at each of the last 12 month ends."""
    day = date.fromisoformat(as_of) if as_of else date.today()
    with _session() as db:
        sheet = networth.sheet(db, day, months=12)
        items = [i for i in sheet.items if i.is_active]
        held = {
            i.holding_id: ibkr.latest_positions(db, i.holding_id, day)
            for i in items
            if i.holding_class == "investment" and i.holding_id is not None
        }
    assets, debts = sheet.total("asset"), sheet.total("liability")
    return {
        "as_of": sheet.as_of.isoformat(),
        "assets": _s(assets),
        "liabilities": _s(debts),
        "net_worth": _s(assets - debts),
        "commitments": _s(sheet.commitments),
        "items": [_item(i, held.get(i.holding_id or -1)) for i in items],
        "net_worth_by_month": [
            {"month": _month(p.month), "net_worth": _s(p.net)} for p in sheet.series
        ],
    }


@mcp.tool()
def loans() -> list[dict[str, Any]]:
    """Each loan with an amortization table: balance, installments paid and left, the next
    installments (principal, interest, other charges), payoff month, and interest paid this year
    and still to pay."""
    today = date.today()
    out = []
    with _session() as db:
        for i in networth.holdings(db, today):
            sched = i.loan.schedule if i.loan else None
            if i.holding_class != "loan" or sched is None or i.holding_id is None:
                continue
            due = [r for r in loan_service.installments(db, i.holding_id) if r.status == "due"]
            out.append(
                {
                    "name": i.name,
                    "balance": None if i.value is None else _s(i.value),
                    "paid": sched.paid,
                    "left": sched.left,
                    "payoff": _month(sched.payoff) if sched.payoff else None,
                    "interest_this_year": _s(sched.interest_this_year),
                    "interest_left": _s(sched.interest_left),
                    "other_charges_left": _s(sched.other_left),
                    "next_installments": [
                        {
                            "month": _month(r.period),
                            "total": _s(r.total),
                            "principal": _s(r.principal),
                            "interest": _s(r.interest),
                            "other": _s(r.other),
                            "balance_after": _s(r.balance_after),
                        }
                        for r in due[:6]
                    ],
                }
            )
    return out


@mcp.tool()
def monthly_report(month: str) -> dict[str, Any]:
    """The saved monthly report for a month (YYYY-MM): its 3 to 5 findings, who wrote them and
    when, and the facts they were written from. Reports are written on the app's Report page;
    this only reads them."""
    m = _m(month)
    with _session() as db:
        r = report_service.get(db, m)
    if r is None:
        return {"month": month, "report": None, "note": "Not written yet: use the Report page."}
    return {
        "month": month,
        "written_by": r.written_by,
        "model": r.model,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        "findings": [{"title": f.title, "text": f.text, "tone": f.tone} for f in r.findings],
        "facts": r.facts,
    }


@mcp.tool()
def data_status(months: int = 3) -> dict[str, Any]:
    """What is missing for the books to be complete, as the app's Data Status page shows it:
    for each of the last `months` months (newest first), the open items (statements not
    uploaded, imports waiting for approval or not tying out, lines needing a category,
    transfers missing the other side, recurring items not paid, balance breaks), and per
    account the statement periods not loaded yet with the statement that fills each one
    (closing day and usual file name; `due` is set when the bank hasn't issued it yet)."""
    with _session() as db:
        st = status_service.month_status(db, with_loads=False)
        gmail = watchdog.script(db)
    names = {a.account_id: a.name for a in st.accounts}
    shown = [m for m in st.months if m.source == "statements"][: max(months, 1)]
    return {
        "today": st.today.isoformat(),
        # The Gmail script that brings statements by email: "silent" means it stopped running
        # and a person must open script.google.com (ADR-078).
        "gmail_script": {
            "state": gmail.state,
            "last_seen": gmail.last_seen.isoformat() if gmail.last_seen else None,
            "note": gmail.note,
        },
        # How each account's data arrives (bank sync, email, upload) and where it stands today:
        # late and you_upload need a person; on_its_way is normal.
        "sources": [
            {
                "account": x.name,
                "how": x.how,
                "state": x.state,
                "last_day": x.last_day.isoformat() if x.last_day else None,
                "expected": x.expected.isoformat() if x.expected else None,
                "note": x.note,
            }
            for x in st.sources
        ],
        "months": [
            {
                "month": _month(m.month),
                "complete": m.complete,
                "items": [{"kind": i.kind, "text": i.text, "count": i.count} for i in m.items],
                "coverage": [
                    {"account": names.get(c.account_id), "state": c.state}
                    for c in m.coverage
                    if c.state != "full"
                ],
            }
            for m in shown
        ],
        "missing_statements": [
            {
                "account": t.name,
                "start": g.start.isoformat(),
                "end": g.end.isoformat(),
                "due": g.due.isoformat() if g.due else None,
                "closes": [c.isoformat() for c in g.closes],
                "files": g.files,
            }
            for t in st.timeline
            for g in t.gaps
        ],
    }


class PositionIn(BaseModel):
    """One position from the IBKR connector's get_account_positions, as it returned it."""

    symbol: str = Field(description="contract_description, e.g. VOO")
    quantity: Decimal = Field(description="position")
    price: Decimal = Field(description="market_price")
    value: Decimal = Field(description="market_value, in the position's currency")
    currency: str = "USD"
    asset_class: str = "STK"
    average_price: Decimal | None = Field(None, description="average_price (cost per unit)")
    unrealized: Decimal | None = Field(None, description="unrealized_pnl")
    description: str | None = None
    fx_rate: Decimal = Field(Decimal(1), description="To USD; 1 for USD positions")


@mcp.tool(
    annotations=ToolAnnotations(
        title="Save the Interactive Brokers portfolio",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def save_portfolio(
    total: Decimal,
    cash: Decimal,
    positions: list[PositionIn],
    as_of: str | None = None,
) -> dict[str, Any]:
    """Save the Interactive Brokers account into the app: its value on the balance sheet and in
    net worth, and its positions. Pass exactly what the IBKR connector returned: `total` is
    get_account_summary's net_liquidation, `cash` its total_cash_value, `positions` every entry
    of get_account_positions. `as_of` is the day (YYYY-MM-DD, default today). Saving a day again
    replaces it. Refused, with nothing saved, when positions plus cash don't tie out to the total
    within 2%, so include every position."""
    day = date.fromisoformat(as_of) if as_of else date.today()
    report = ibkr.from_connector(
        day,
        total,
        cash,
        [ibkr.ConnectorPosition(**p.model_dump()) for p in positions],
    )
    with Session(get_writer_engine()) as db:
        saved = ibkr.store(db, report, "claude (IBKR connector)")
        p = ibkr.portfolio(db)
    return {
        "saved": True,
        "as_of": saved.as_of.isoformat(),
        "total": _s(saved.total),
        "cash": _s(saved.cash),
        "positions": saved.positions,
        "previous": None
        if p.previous_total is None or p.previous_as_of is None
        else {"as_of": p.previous_as_of.isoformat(), "total": _s(p.previous_total)},
    }


@mcp.tool()
def purchases(month: str, top: int = 15) -> dict[str, Any]:
    """What was bought in a month (YYYY-MM) according to electronic invoices: total, spending by
    product group (Meat & Fish, Dairy & Eggs, Baby, Household & Cleaning…), the top products by
    amount, and each vendor's invoices. Covers only invoices received, not all spending."""
    m = _m(month)
    with _session() as db:
        groups = invoices.month_groups(db, m)
        invs = invoices.month_invoices(db, m)
        products: dict[str, dict[str, Any]] = {}
        vendors: dict[str, dict[str, Any]] = {}
        for inv in invs:
            v = vendors.setdefault(inv.issuer_name, {"invoices": 0, "amount": ZERO})
            v["invoices"] += 1
            v["amount"] += inv.total
            for ln in inv.lines:
                p = products.setdefault(
                    ln.product_key,
                    {
                        "product": ln.description,
                        "group": ln.product_group,
                        "qty": ZERO,
                        "amt": ZERO,
                    },
                )
                p["qty"] += ln.quantity
                p["amt"] += ln.total
    ranked = sorted(products.values(), key=lambda p: -p["amt"])[: max(1, min(top, 50))]
    return {
        "month": month,
        "invoices": len(invs),
        "total": _s(sum((i.total for i in invs), ZERO)),
        "by_group": [{"group": g.group, "amount": _s(g.amount), "lines": g.lines} for g in groups],
        "top_products": [
            {
                "product": p["product"],
                "group": p["group"],
                "quantity": format(p["qty"].normalize(), "f"),
                "amount": _s(p["amt"]),
            }
            for p in ranked
        ],
        "vendors": [
            {"vendor": k, "invoices": v["invoices"], "amount": _s(v["amount"])}
            for k, v in sorted(vendors.items(), key=lambda kv: -kv[1]["amount"])
        ],
    }


def _plain(v: Any) -> Any:
    """A service's dataclasses as JSON: money and dates as text."""
    if is_dataclass(v) and not isinstance(v, type):
        return {f.name: _plain(getattr(v, f.name)) for f in fields(v)}
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list | tuple | set):
        return [_plain(x) for x in v]
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


@mcp.tool()
def taxes(year: int) -> dict[str, Any]:
    """Gastos personales for a tax year, as the app's Taxes page shows them: for Hernan and
    Lauren, the deductible invoices by SRI category (vivienda, educacion, salud, alimentacion,
    vestimenta, turismo), the cap their cargas familiares allow, the deductible amount and the
    18% rebate, how many invoices still need a category, and invoices with no person yet.
    Amounts are before IVA. Nothing here is filed with the SRI."""
    with _session() as db:
        return dict(_plain(gastos.summary(db, year)))


@mcp.tool()
def iva_return(month: str, person: str = "Hernan") -> dict[str, Any]:
    """The monthly IVA return (Form 104) the app prepares for a person and month (YYYY-MM):
    the form's fields (401 sales, 411/421 IVA charged, 500/510/520 purchases, 601-620 credit and
    tax due), sales issued, withholdings received, credit and debit notes, and the 30 largest
    purchases (the rest are counted). Credit carries from the opening month entered in the app."""
    with _session() as db:
        r = iva.month(db, person, _m(month))
    out = dict(_plain(r))
    purchases = sorted(out.pop("purchases"), key=lambda p: -Decimal(p.get("total") or 0))
    out["purchases"] = purchases[:30]
    out["purchases_count"] = len(purchases)
    return out


@mcp.tool()
def groceries_trends(month: str, months: int = 12) -> dict[str, Any]:
    """Supermarket spending up to a month (YYYY-MM): for each of the last `months` months
    (6 to 24), the statements' Groceries spending, what the supermarket invoices bought by aisle,
    trips and average basket; spending by day of the week; products whose unit price went up or
    down the most; products first bought this month; regulars not bought this month. Also this
    month's stores and the grocery charges whose invoice hasn't arrived."""
    m = _m(month)
    with _session() as db:
        t = groceries.trends(db, m, months)
        g = groceries.build(db, m)
    out = dict(_plain(t))
    out.pop("cells", None)  # by month, aisle, type and brand: groceries_products has those
    out["this_month"] = {
        "spent": _s(g.spent),
        "usual": _s(g.usual),
        "invoiced": _s(g.invoiced),
        "stores": _plain(g.stores),
        "missing_invoices": _plain(g.missing),
    }
    return out


@mcp.tool()
def groceries_products(month: str, months: int = 1) -> dict[str, Any]:
    """What the supermarket invoices bought in a month (YYYY-MM), or the `months` up to it:
    totals by aisle, by type of product (milk, rice, chicken…) and by brand, and the 40 products
    that cost the most with quantity and unit price. Labels come from rules a person confirmed or
    Claude suggested in the app; `unlabeled` counts products without a type yet."""
    with _session() as db:
        p = product_labels.products(db, _m(month), max(1, min(months, 24)))
    out = dict(_plain(p))
    out["products"] = out["products"][:40]
    return out


@mcp.tool()
def bills(month: str) -> dict[str, Any]:
    """The bills, subscriptions and recurring income due in a month (YYYY-MM), as the app's
    Bills & subscriptions page shows them: expected and paid amount (signed: negative = money
    out), status (paid, due, late, skipped), due day, account, the average of the three months
    before and payments left when the item has an end."""
    m = _m(month)
    with _session() as db:
        rows = recurring_service.bills(db, m, date.today())
    return {"month": _month(m), "bills": _plain(rows)}


@mcp.tool()
def budget(month: str) -> dict[str, Any]:
    """The month's budget (YYYY-MM) by group: budget, carried over, spent, left, the pace
    allowed by today and status (over, ahead, on_track); spending in groups without a budget;
    and every savings goal with its progress, the monthly amount needed and whether it's on pace."""
    m = _m(month)
    with _session() as db:
        b = budget_service.month_view(db, m)
        g = goals.all_goals(db)
    return {"budget": _plain(b), "goals": _plain(g)}


def get_writer_engine() -> Any:
    """The app's own login, for save_portfolio only (a seam the tests replace)."""
    return get_engine()


def http_endpoint() -> tuple[Route, StreamableHTTPSessionManager]:
    """A /mcp route and its session manager for one app instance (each app runs its own
    manager in its lifespan; a manager can only run once)."""
    manager = StreamableHTTPSessionManager(
        app=mcp._mcp_server,
        json_response=True,
        stateless=True,
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return Route("/mcp", endpoint=StreamableHTTPASGIApp(manager)), manager
