# ruff: noqa: E501  (the Flex XML fixture keeps IBKR's long element lines)
"""F22: the Interactive Brokers portfolio from a Flex report: reading it, IBKR's two-step Flex Web
Service (with "still generating"), storing a day, the page's endpoints and Claude's view.
Synthetic reports only."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import mcp_server
from app.config import get_settings
from app.models import BalanceSnapshot, InvestmentPosition
from app.services import ibkr

USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def flex(day: str = "2026-10-28", total: str = "25350.40", eur_rate: str = "1.08") -> bytes:
    return f"""<FlexQueryResponse queryName="cashflow-app" type="AF">
<FlexStatements count="1">
<FlexStatement accountId="U0000000" fromDate="{day}" toDate="{day}" period="LastBusinessDay">
<EquitySummaryInBase>
  <EquitySummaryByReportDateInBase reportDate="2026-10-27" cash="400.00" stock="24000.00" total="24400.00"/>
  <EquitySummaryByReportDateInBase reportDate="{day}" cash="350.40" stock="25000.00" total="{total}"/>
</EquitySummaryInBase>
<OpenPositions>
  <OpenPosition symbol="VT" description="VANGUARD TOT WORLD STK ETF" assetCategory="STK" currency="USD"
    position="150" markPrice="120.50" positionValue="18075.00" costBasisMoney="15000.00"
    fifoPnlUnrealized="3075.00" fxRateToBase="1" reportDate="{day}" levelOfDetail="SUMMARY"/>
  <OpenPosition symbol="VT" description="VANGUARD TOT WORLD STK ETF" assetCategory="STK" currency="USD"
    position="100" markPrice="120.50" positionValue="12050.00" levelOfDetail="LOT"/>
  <OpenPosition symbol="IWDA" description="ISHARES CORE MSCI WORLD" assetCategory="STK" currency="EUR"
    position="80" markPrice="80.00" positionValue="6400.00" costBasisMoney="6000.00"
    fifoPnlUnrealized="400.00" fxRateToBase="{eur_rate}" reportDate="{day}"/>
  <OpenPosition symbol="BAD" assetCategory="STK" currency="USD" position="" positionValue="--"/>
</OpenPositions>
<CashReport>
  <CashReportCurrency currency="BASE_SUMMARY" endingCash="999.99"/>
</CashReport>
</FlexStatement>
</FlexStatements>
</FlexQueryResponse>""".encode()


def answer(status: str, code: str = "", message: str = "") -> bytes:
    if status == "Success":
        return (
            b"<FlexStatementResponse timestamp='x'><Status>Success</Status>"
            b"<ReferenceCode>123456</ReferenceCode>"
            b"<Url>https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/"
            b"GetStatement</Url></FlexStatementResponse>"
        )
    return (
        f"<FlexStatementResponse><Status>Fail</Status><ErrorCode>{code}</ErrorCode>"
        f"<ErrorMessage>{message}</ErrorMessage></FlexStatementResponse>"
    ).encode()


def mock(*bodies: bytes) -> tuple[httpx.Client, list[str]]:
    seen: list[str] = []
    queue = list(bodies)

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.url.path.rsplit('/', 1)[-1]} q={request.url.params['q']}")
        return httpx.Response(200, content=queue.pop(0))

    return httpx.Client(transport=httpx.MockTransport(handle)), seen


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("IBKR_FLEX_TOKEN", "test-token")
    monkeypatch.setenv("IBKR_FLEX_QUERY_ID", "999")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("IBKR_FLEX_TOKEN")
    monkeypatch.delenv("IBKR_FLEX_QUERY_ID")
    get_settings.cache_clear()


# ---------------------------------------------------------------- reading a report
def test_parse() -> None:
    r = ibkr.parse(flex())
    assert (r.as_of, r.total, r.cash) == (
        date(2026, 10, 28),
        Decimal("25350.40"),
        Decimal("350.40"),
    )
    assert [p.symbol for p in r.positions] == ["VT", "IWDA"]  # the lot and the broken row skipped
    vt, iwda = r.positions
    assert (vt.quantity, vt.price, vt.value, vt.unrealized) == (
        Decimal(150),
        Decimal("120.50"),
        Decimal("18075.00"),
        Decimal("3075.00"),
    )
    assert (iwda.currency, iwda.value, iwda.cost_basis) == (
        "EUR",
        Decimal("6912.00"),
        Decimal("6480.00"),
    )


def test_parse_without_nav_and_errors() -> None:
    no_nav = flex().replace(b"EquitySummaryByReportDateInBase", b"Ignored")
    r = ibkr.parse(no_nav)
    assert r.cash == Decimal("999.99") and r.as_of == date(2026, 10, 28)
    assert r.total == Decimal("18075.00") + Decimal("6912.00") + Decimal("999.99")
    with pytest.raises(ibkr.IbkrError, match="isn't a Flex report"):
        ibkr.parse(b"not xml")
    with pytest.raises(ibkr.IbkrError, match="no statement"):
        ibkr.parse(b"<FlexQueryResponse/>")
    with pytest.raises(ibkr.IbkrError, match=r"IBKR: Token is invalid. \(code 1015\)"):
        ibkr.parse(answer("Fail", "1015", "Token is invalid."))
    assert ibkr._date("20261028") == date(2026, 10, 28) and ibkr._date("bad") is None


# ---------------------------------------------------------------- the Flex Web Service
def test_fetch_waits_while_generating() -> None:
    client, seen = mock(
        answer("Success"), answer("Fail", "1019", "Statement generation in progress."), flex()
    )
    waits: list[float] = []
    body = ibkr.fetch("tok", "999", client, sleep=waits.append)
    assert body.startswith(b"<FlexQueryResponse")
    assert seen == ["SendRequest q=999", "GetStatement q=123456", "GetStatement q=123456"]
    assert waits == [ibkr.WAIT_SECONDS]


def test_fetch_failures() -> None:
    client, _ = mock(answer("Fail", "1012", "Token has expired."))
    with pytest.raises(ibkr.IbkrError, match="Token has expired"):
        ibkr.fetch("tok", "999", client, sleep=lambda s: None)
    client, _ = mock(answer("Success"), answer("Fail", "1015", "Token is invalid."))
    with pytest.raises(ibkr.IbkrError, match="code 1015"):
        ibkr.fetch("tok", "999", client, sleep=lambda s: None)
    busy = answer("Fail", "1019", "Statement generation in progress.")
    client, _ = mock(answer("Success"), *[busy] * ibkr.ATTEMPTS)
    with pytest.raises(ibkr.IbkrError, match="still generating"):
        ibkr.fetch("tok", "999", client, sleep=lambda s: None)
    client, _ = mock(b"<<<")
    with pytest.raises(ibkr.IbkrError, match="could not be read"):
        ibkr.fetch("tok", "999", client, sleep=lambda s: None)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(ibkr.IbkrError, match="could not be reached: ConnectError"):
        ibkr.fetch("tok", "999", httpx.Client(transport=httpx.MockTransport(down)))


# ---------------------------------------------------------------- storing and the page
def test_upload_store_and_portfolio(client: TestClient, db: Session) -> None:
    empty = client.get("/api/investments/ibkr").json()
    assert empty["configured"] is False and empty["holding_id"] is None and not empty["stale"]

    files = {"file": ("flex.xml", flex("2026-10-27", "24400.00"), "text/xml")}
    first = client.post("/api/investments/ibkr/upload", files=files, headers=USER)
    assert first.status_code == 200, first.text
    files = {"file": ("flex.xml", flex(), "text/xml")}
    out = client.post("/api/investments/ibkr/upload", files=files, headers=USER).json()
    assert out["as_of"] == "2026-10-28" and Decimal(out["total"]) == Decimal("25350.40")
    assert out["positions"] == 2
    # The same day again replaces it.
    client.post("/api/investments/ibkr/upload", files=files, headers=USER)
    assert (
        db.scalar(select(func.count()).select_from(InvestmentPosition)) == 4
    )  # 2 days x 2 positions

    p = client.get("/api/investments/ibkr").json()
    assert (p["as_of"], Decimal(p["total"]), Decimal(p["cash"])) == (
        "2026-10-28",
        Decimal("25350.40"),
        Decimal("350.40"),
    )
    assert (p["previous_as_of"], Decimal(p["previous_total"])) == ("2026-10-27", Decimal("24400"))
    assert [x["symbol"] for x in p["positions"]] == ["VT", "IWDA"]

    # It is on the balance sheet like any value, and Claude sees the positions.
    items = client.get("/api/networth", params={"as_of": "2026-10-29"}).json()["items"]
    ib = next(i for i in items if i["name"] == "Interactive Brokers")
    assert ib["holding_class"] == "investment" and Decimal(ib["value"]) == Decimal("25350.40")
    assert ib["source"] == "ibkr"
    snaps = db.scalars(select(BalanceSnapshot).where(BalanceSnapshot.source == "ibkr")).all()
    assert len(snaps) == 2

    bad = client.post(
        "/api/investments/ibkr/upload", files={"file": ("x.xml", b"nope", "text/xml")}
    )
    assert bad.status_code == 422
    big = {"file": ("x.xml", b"x" * (10 * 1024 * 1024 + 1), "text/xml")}
    assert client.post("/api/investments/ibkr/upload", files=big).status_code == 413


def test_claude_sees_positions(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_server, "get_reader_engine", lambda: engine)
    client.post("/api/investments/ibkr/upload", files={"file": ("f.xml", flex(), "text/xml")})
    sheet = mcp_server.balance_sheet("2026-10-29")
    ib = next(i for i in sheet["items"] if i["name"] == "Interactive Brokers")
    assert ib["positions"][0] == {
        "symbol": "VT",
        "description": "VANGUARD TOT WORLD STK ETF",
        "quantity": "150",
        "price": "120.5",
        "value": "18075.00",
        "unrealized": "3075.00",
    }


def test_refresh(
    client: TestClient, db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    def fake(token: str, query: str, client: Any = None) -> bytes:
        calls.append((token, query))
        return flex()

    monkeypatch.setattr(ibkr, "fetch", fake)
    assert client.get("/api/investments/ibkr").json()["stale"] is True  # set up, never read
    out = client.post("/api/investments/ibkr/refresh", headers=USER)
    assert out.status_code == 200, out.text
    assert calls == [("test-token", "999")]
    p = ibkr.portfolio(db)
    assert p.configured and not p.stale and p.total == Decimal("25350.40")
    assert ibkr.portfolio(db, now=datetime.now() + timedelta(days=2)).stale

    def broken(token: str, query: str, client: Any = None) -> bytes:
        raise ibkr.IbkrError("IBKR: Token has expired. (code 1012)")

    monkeypatch.setattr(ibkr, "fetch", broken)
    resp = client.post("/api/investments/ibkr/refresh")
    assert resp.status_code == 502 and "expired" in resp.json()["detail"]


def test_refresh_not_set_up(client: TestClient) -> None:
    resp = client.post("/api/investments/ibkr/refresh")
    assert resp.status_code == 503 and "setup-ibkr.sh" in resp.json()["detail"]
