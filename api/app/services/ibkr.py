"""Interactive Brokers portfolio (F22, ADR-019): positions, cash and net asset value from IBKR's
read-only Flex Web Service.

Hernan creates an Activity Flex Query once in Client Portal (Net Asset Value in Base, Open
Positions as Summary, Cash Report; XML; last business day) and a Flex Web Service token. The app
asks IBKR to run the query (SendRequest), then downloads the report (GetStatement), retrying while
IBKR says it is still being generated. The report is read into:
- one balance snapshot for the report's day (source 'ibkr') on the "Interactive Brokers"
  investment holding, its net asset value (created on the first read), so it counts on the balance
  sheet and in net worth like any other value;
- that day's positions (core.investment_position), replaced when the same day is read again.

Values are USD (the account's base currency; a position in another currency is converted with the
report's own rate). The account number isn't stored. A Flex XML downloaded from Client Portal can
be uploaded instead, e.g. if the token expired.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, BalanceSnapshot, Holding, InvestmentPosition

BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
SOURCE = "ibkr"
HOLDING_NAME = "Interactive Brokers"
HOLDING_KEY = "ibkr_holding_id"
STALE = timedelta(hours=20)
RETRY_CODES = {"1001", "1004", "1009", "1019"}  # "try again shortly" / still generating
WAIT_SECONDS = 5
ATTEMPTS = 12
CENT = Decimal("0.01")
ZERO = Decimal(0)


class IbkrError(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Position:
    symbol: str
    description: str | None
    asset_class: str
    currency: str
    quantity: Decimal
    price: Decimal
    value: Decimal  # in the base currency (USD)
    cost_basis: Decimal | None
    unrealized: Decimal | None


@dataclass
class Report:
    as_of: date
    total: Decimal
    cash: Decimal
    positions: list[Position] = field(default_factory=list)


def _dec(text: str | None) -> Decimal | None:
    if text is None or text.strip() in ("", "--"):
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _date(text: str | None) -> date | None:
    if not text:
        return None
    raw = text.split(";")[0].strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse(xml: bytes) -> Report:
    """Read an Activity Flex report (XML)."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise IbkrError("This isn't a Flex report (XML).", 422) from exc
    if root.tag == "FlexStatementResponse":  # an error answer, not a report
        raise IbkrError(_error(root), 502)
    statements = root.findall(".//FlexStatement")
    if not statements:
        raise IbkrError("The Flex report has no statement in it.", 422)
    st = statements[0]

    navs = []
    for n in st.iter("EquitySummaryByReportDateInBase"):
        d, total = _date(n.get("reportDate")), _dec(n.get("total"))
        if d and total is not None:
            navs.append((d, total, _dec(n.get("cash")) or ZERO))
    positions = []
    for p in st.iter("OpenPosition"):
        if p.get("levelOfDetail", "SUMMARY").upper() not in ("SUMMARY", ""):
            continue  # lots repeat the summary
        qty, price = _dec(p.get("position")), _dec(p.get("markPrice"))
        local = _dec(p.get("positionValue"))
        if qty is None or local is None:
            continue
        rate = _dec(p.get("fxRateToBase")) or Decimal(1)
        positions.append(
            Position(
                symbol=(p.get("symbol") or "?")[:40],
                description=(p.get("description") or None) and p.get("description", "")[:200],
                asset_class=(p.get("assetCategory") or "OTHER")[:20],
                currency=(p.get("currency") or "USD")[:3],
                quantity=qty,
                price=price or ZERO,
                value=(local * rate).quantize(CENT),
                cost_basis=_q(_dec(p.get("costBasisMoney")), rate),
                unrealized=_q(_dec(p.get("fifoPnlUnrealized")), rate),
            )
        )
    cash = ZERO
    for c in st.iter("CashReportCurrency"):
        if c.get("currency") == "BASE_SUMMARY":
            cash = _dec(c.get("endingCash")) or ZERO
    if navs:
        as_of, total, nav_cash = max(navs, key=lambda n: n[0])
        cash = nav_cash or cash
    else:  # no NAV section: positions plus cash
        as_of = _date(st.get("toDate")) or date.today()
        total = sum((p.value for p in positions), ZERO) + cash
    return Report(as_of, total.quantize(CENT), cash.quantize(CENT), positions)


def _q(v: Decimal | None, rate: Decimal) -> Decimal | None:
    return None if v is None else (v * rate).quantize(CENT)


def _error(root: ElementTree.Element) -> str:
    code = (root.findtext("ErrorCode") or "").strip()
    message = (root.findtext("ErrorMessage") or "IBKR refused the request.").strip()
    return f"IBKR: {message}" + (f" (code {code})" if code else "")


# ---------------------------------------------------------------- fetching
def fetch(
    token: str,
    query_id: str,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Run the Flex Query and download its report, waiting while IBKR generates it."""
    http = client or httpx.Client(timeout=60, headers={"User-Agent": "household-cashflow"})
    try:
        r = http.get(f"{BASE}/SendRequest", params={"t": token, "q": query_id, "v": "3"})
        r.raise_for_status()
        root = ElementTree.fromstring(r.content)
        if (root.findtext("Status") or "").strip() != "Success":
            raise IbkrError(_error(root))
        ref = (root.findtext("ReferenceCode") or "").strip()
        url = (root.findtext("Url") or f"{BASE}/GetStatement").strip()
        for attempt in range(ATTEMPTS):
            r = http.get(url, params={"t": token, "q": ref, "v": "3"})
            r.raise_for_status()
            body = r.content
            if b"<FlexQueryResponse" in body[:500]:
                return body
            root = ElementTree.fromstring(body)
            if (root.findtext("ErrorCode") or "").strip() not in RETRY_CODES:
                raise IbkrError(_error(root))
            if attempt < ATTEMPTS - 1:
                sleep(WAIT_SECONDS)
        raise IbkrError("IBKR is still generating the report; try again in a minute.")
    except httpx.HTTPError as exc:
        raise IbkrError(f"IBKR could not be reached: {exc.__class__.__name__}.") from exc
    except ElementTree.ParseError as exc:
        raise IbkrError("IBKR's answer could not be read.") from exc
    finally:
        if client is None:
            http.close()


def configured() -> bool:
    s = get_settings()
    return bool(s.ibkr_flex_token and s.ibkr_flex_query_id)


# ---------------------------------------------------------------- storing
def holding(db: Session, create: bool = False) -> Holding | None:
    """The investment holding the IBKR values go to: the one chosen before, else one named
    "Interactive Brokers", created on the first read."""
    s = db.get(AppSetting, HOLDING_KEY)
    h = db.get(Holding, int(s.setting_value)) if s else None
    if h is None:
        h = db.scalar(select(Holding).where(Holding.name == HOLDING_NAME))
    if h is None and create:
        h = Holding(name=HOLDING_NAME, side="asset", holding_class="investment", is_active=True)
        db.add(h)
        db.flush()
    if h is not None and s is None:
        db.add(
            AppSetting(setting_key=HOLDING_KEY, setting_value=str(h.holding_id), updated_by="ibkr")
        )
        db.flush()
    return h


@dataclass
class Imported:
    holding_id: int
    as_of: date
    total: Decimal
    cash: Decimal
    positions: int


def store(db: Session, report: Report, user: str) -> Imported:
    h = holding(db, create=True)
    assert h is not None
    db.execute(
        delete(InvestmentPosition).where(
            InvestmentPosition.holding_id == h.holding_id, InvestmentPosition.as_of == report.as_of
        )
    )
    db.execute(
        delete(BalanceSnapshot).where(
            BalanceSnapshot.holding_id == h.holding_id,
            BalanceSnapshot.source == SOURCE,
            BalanceSnapshot.as_of == report.as_of,
        )
    )
    db.add(
        BalanceSnapshot(
            as_of=report.as_of,
            name=h.name[:100],
            kind="asset",
            amount=report.total,
            source=SOURCE,
            holding_id=h.holding_id,
            notes=f"Cash {report.cash}; {len(report.positions)} positions; read by {user}"[:400],
        )
    )
    db.add_all(
        InvestmentPosition(
            holding_id=h.holding_id,
            as_of=report.as_of,
            symbol=p.symbol,
            description=p.description,
            asset_class=p.asset_class,
            currency=p.currency,
            quantity=p.quantity,
            price=p.price,
            value=p.value,
            cost_basis=p.cost_basis,
            unrealized=p.unrealized,
        )
        for p in report.positions
    )
    db.commit()
    return Imported(h.holding_id, report.as_of, report.total, report.cash, len(report.positions))


def refresh(db: Session, user: str, client: httpx.Client | None = None) -> Imported:
    if not configured():
        raise IbkrError(
            "IBKR isn't set up: run infra/azure/setup-ibkr.sh (or set IBKR_FLEX_TOKEN and "
            "IBKR_FLEX_QUERY_ID).",
            503,
        )
    s = get_settings()
    return store(db, parse(fetch(s.ibkr_flex_token, s.ibkr_flex_query_id, client)), user)


# ---------------------------------------------------------------- reading
@dataclass
class Portfolio:
    configured: bool
    holding_id: int | None
    as_of: date | None
    total: Decimal | None
    cash: Decimal | None
    previous_total: Decimal | None
    previous_as_of: date | None
    stale: bool
    positions: list[InvestmentPosition] = field(default_factory=list)


def latest_positions(
    db: Session, holding_id: int, as_of: date | None = None
) -> list[InvestmentPosition]:
    q = select(func.max(InvestmentPosition.as_of)).where(
        InvestmentPosition.holding_id == holding_id
    )
    if as_of is not None:
        q = q.where(InvestmentPosition.as_of <= as_of)
    day = db.scalar(q)
    if day is None:
        return []
    return list(
        db.scalars(
            select(InvestmentPosition)
            .where(InvestmentPosition.holding_id == holding_id, InvestmentPosition.as_of == day)
            .order_by(InvestmentPosition.value.desc(), InvestmentPosition.symbol)
        )
    )


def portfolio(db: Session, now: datetime | None = None) -> Portfolio:
    now = now or datetime.now()
    h = holding(db)
    if h is None:
        return Portfolio(configured(), None, None, None, None, None, None, configured())
    snaps = list(
        db.scalars(
            select(BalanceSnapshot)
            .where(BalanceSnapshot.holding_id == h.holding_id, BalanceSnapshot.source == SOURCE)
            .order_by(BalanceSnapshot.as_of.desc())
            .limit(2)
        )
    )
    last = snaps[0] if snaps else None
    before = snaps[1] if len(snaps) > 1 else None
    read_at = last.updated_at if last is not None and last.updated_at else None
    stale = configured() and (read_at is None or now - read_at > STALE)
    cash = None
    if last is not None and last.notes and last.notes.startswith("Cash "):
        cash = _dec(last.notes[5:].split(";")[0])
    return Portfolio(
        configured(),
        h.holding_id,
        last.as_of if last else None,
        last.amount if last else None,
        cash,
        before.amount if before else None,
        before.as_of if before else None,
        stale,
        latest_positions(db, h.holding_id),
    )
