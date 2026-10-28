"""Claude's read-only MCP endpoint (F18, ADR-017): the household's analysis views as tools.

Served at /mcp by the app (streamable HTTP, stateless, JSON responses), behind a bearer token
(MCP_TOKEN, checked in app.auth). Every tool reads the `mart` views through the read-only
`cashflow_reader` login (app.db.reader): nothing here can change data or read a table directly.
Months are "YYYY-MM"; amounts are USD strings with two decimals.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, select
from starlette.routing import Route

from app.db.reader import get_reader_engine
from app.models import (
    v_category_month,
    v_debt_cost,
    v_monthly_cash,
    v_monthly_cashflow,
    v_spending_line,
)
from app.services.classify import merchant_key

CENT = Decimal("0.01")
ZERO = Decimal(0)
MAX_LINES = 500

INSTRUCTIONS = """\
Read-only access to Hernan and Lauren's household cash flow (Quito, Ecuador; USD, the country is
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
