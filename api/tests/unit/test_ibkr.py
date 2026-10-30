# ruff: noqa: E501  (the Flex XML fixture keeps IBKR's long element lines)
"""F22: the Interactive Brokers portfolio. Claude saving what the IBKR connector returned
(save_portfolio, with its tie-out), a Flex report uploaded by hand, storing a day, the page's
endpoint and Claude's view. Synthetic accounts only."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import mcp_server
from app.config import get_settings
from app.main import create_app
from app.models import BalanceSnapshot, InvestmentPosition, LoadLog
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
    refused = (
        b"<FlexStatementResponse><Status>Fail</Status><ErrorCode>1015</ErrorCode>"
        b"<ErrorMessage>Token is invalid.</ErrorMessage></FlexStatementResponse>"
    )
    with pytest.raises(ibkr.IbkrError, match=r"IBKR: Token is invalid. \(code 1015\)"):
        ibkr.parse(refused)
    assert ibkr._date("20261028") == date(2026, 10, 28) and ibkr._date("bad") is None


# ---------------------------------------------------------------- storing and the page
def test_upload_store_and_portfolio(client: TestClient, db: Session) -> None:
    empty = client.get("/api/investments/ibkr").json()
    assert empty["holding_id"] is None and empty["positions"] == [] and not empty["stale"]

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


# ---------------------------------------------------------------- Claude, through the connector
TOKEN = "t" * 48


def connector_positions() -> list[dict[str, Any]]:
    """Shaped like the IBKR connector's get_account_positions, mapped to save_portfolio's fields."""
    return [
        {"symbol": "VOO", "quantity": "3", "price": "700", "value": "2100",
         "average_price": "550", "unrealized": "450"},
        {"symbol": "VT", "quantity": "7.5", "price": "140", "value": "1050",
         "average_price": "130", "unrealized": "75"},
        {"symbol": "IWDA", "quantity": "10", "price": "100", "value": "1000", "currency": "eur",
         "fx_rate": "1.08", "description": "ISHARES CORE MSCI WORLD"},
    ]  # fmt: skip


def save(**kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "total": Decimal("4300.00"),
        "cash": Decimal("34"),
        "positions": [mcp_server.PositionIn(**p) for p in connector_positions()],
        "as_of": "2026-10-29",
    } | kw
    return mcp_server.save_portfolio(**args)


@pytest.fixture
def writer(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    monkeypatch.setattr(mcp_server, "get_writer_engine", lambda: engine)
    monkeypatch.setattr(mcp_server, "get_reader_engine", lambda: engine)
    return engine


def test_from_connector() -> None:
    raw = [ibkr.ConnectorPosition(**mcp_server.PositionIn(**p).model_dump())
           for p in connector_positions()]  # fmt: skip
    r = ibkr.from_connector(date(2026, 10, 29), Decimal("4300"), Decimal("34"), raw)
    voo, _, iwda = r.positions
    assert (voo.cost_basis, voo.unrealized) == (Decimal("1650.00"), Decimal("450.00"))
    assert (iwda.currency, iwda.value, iwda.cost_basis) == ("EUR", Decimal("1080.00"), None)
    assert iwda.description == "ISHARES CORE MSCI WORLD" and voo.description is None
    # 2100 + 1050 + 1080 + 34 = 4264: 36 from the total, within 2%.
    assert r.total == Decimal("4300.00")
    with pytest.raises(ibkr.IbkrError, match="don't tie out") as exc:
        ibkr.from_connector(date(2026, 10, 29), Decimal("6000"), Decimal("34"), raw)
    assert exc.value.status == 422 and "Nothing was saved" in str(exc.value)
    with pytest.raises(ibkr.IbkrError, match="in the future"):
        ibkr.from_connector(date.today() + timedelta(days=3), Decimal("4300"), Decimal(0), raw)
    with pytest.raises(ibkr.IbkrError, match="above zero"):
        ibkr.from_connector(date(2026, 10, 29), Decimal(0), Decimal(0), [])


def test_save_portfolio(writer: Engine, db: Session, client: TestClient) -> None:
    first = save(as_of="2026-10-28", total=Decimal("4250"))
    assert first["previous"] is None
    out = save()
    assert out == {
        "saved": True,
        "as_of": "2026-10-29",
        "total": "4300.00",
        "cash": "34.00",
        "positions": 3,
        "previous": {"as_of": "2026-10-28", "total": "4250.00"},
    }
    save()  # the same day again replaces it
    assert db.scalar(select(func.count()).select_from(InvestmentPosition)) == 6
    logs = db.scalars(select(LoadLog).where(LoadLog.source == "ibkr")).all()
    assert len(logs) == 3 and logs[-1].loaded_by == "claude (IBKR connector)"
    assert logs[-1].summary == "IBKR portfolio 2026-10-29: total 4300.00, cash 34.00"

    p = client.get("/api/investments/ibkr").json()
    assert (p["as_of"], p["positions"][0]["symbol"], p["stale"]) == ("2026-10-29", "VOO", False)
    item = next(
        i for i in mcp_server.balance_sheet("2026-10-29")["items"]
        if i["name"] == "Interactive Brokers"
    )  # fmt: skip
    assert item["value"] == "4300.00" and len(item["positions"]) == 3

    with pytest.raises(ibkr.IbkrError, match="don't tie out"):
        save(positions=[])
    assert db.scalar(select(func.count()).select_from(LoadLog).where(LoadLog.source == "ibkr")) == 3


def test_stale_after_a_week(writer: Engine, db: Session) -> None:
    save()
    assert not ibkr.portfolio(db).stale
    assert ibkr.portfolio(db, now=datetime.now() + timedelta(days=8)).stale


def test_save_portfolio_over_mcp(writer: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TOKEN", TOKEN)
    get_settings.cache_clear()
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    def rpc(method: str, params: dict[str, Any]) -> Any:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = client.post("/mcp", headers=headers, json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()["result"]

    try:
        with TestClient(create_app()) as client:
            tools = {t["name"]: t for t in rpc("tools/list", {})["tools"]}
            tool = tools["save_portfolio"]
            assert tool["annotations"]["readOnlyHint"] is False
            assert "net_liquidation" in tool["description"]
            args = {"total": 4300, "cash": 34, "positions": connector_positions()}
            done = rpc("tools/call", {"name": "save_portfolio", "arguments": args})
            assert not done.get("isError"), done
            got = done.get("structuredContent") or json.loads(done["content"][0]["text"])
            assert got["saved"] and got["positions"] == 3
            refused = rpc(
                "tools/call",
                {"name": "save_portfolio", "arguments": args | {"positions": []}},
            )
            assert refused["isError"] and "don't tie out" in refused["content"][0]["text"]
    finally:
        monkeypatch.delenv("MCP_TOKEN")
        get_settings.cache_clear()
