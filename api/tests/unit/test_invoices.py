"""F21: electronic invoices. Reading SRI XML (wrapped or bare, safe against hostile XML), storing
once, matching the card line that paid it, product groups (keywords, Claude, a person's rule),
the Purchases endpoints, the Gmail inbox and Claude's purchases tool. Synthetic invoices only."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import mcp_server
from app.config import get_settings
from app.models import Account, Category, Invoice, InvoiceLine, LoadLog, ProductRule, Transaction
from app.services import invoices, product_suggest
from tests.fixtures.invoices import KEY, TOTAL, factura

XML = "application/xml"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}
OTHER_KEY = "3110202601179999999900120721400001234571234567815"


def card_line(db: Session, day: date, amount: Decimal, n: int = 1) -> Transaction:
    acct = db.scalar(select(Account).where(Account.name == "Capital One Venture"))
    cat = db.scalar(select(Category).where(Category.name == "Supermarket"))
    assert acct is not None and cat is not None
    t = Transaction(
        natural_key=f"inv-{day}-{amount}-{n}",
        account_id=acct.account_id,
        txn_date=day,
        cash_month=day.replace(day=1),
        amount=-amount,
        description_raw="SUPER PRUEBA 072",
        merchant="SUPER PRUEBA",
        type="expense",
        category_id=cat.category_id,
        source="manual",
        status="confirmed",
    )
    db.add(t)
    db.commit()
    return t


def upload(client: TestClient, *files: tuple[str, bytes]) -> list[dict]:  # type: ignore[type-arg]
    resp = client.post(
        "/api/invoices", files=[("files", (n, d, XML)) for n, d in files], headers=USER
    )
    assert resp.status_code == 200, resp.text
    return resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------- reading
def test_parse_wrapped_and_bare() -> None:
    p = invoices.parse(factura())
    assert (p.access_key, p.number, p.issue_date) == (KEY, "072-140-000123456", date(2026, 10, 28))
    assert (p.issuer_name, p.subtotal, p.tax, p.total) == (
        "SUPER PRUEBA",
        Decimal("15.00"),
        Decimal("0.98"),
        TOTAL,
    )
    det = p.lines[2]
    assert (det.description, det.subtotal, det.tax, det.total) == (
        "DETERGENTE POLVO 2KG",
        Decimal("6.50"),
        Decimal("0.98"),
        Decimal("7.48"),
    )
    assert invoices.parse(factura(wrapped=False)).total == TOTAL
    namespaced = factura(wrapped=False).replace(
        b'<factura id="comprobante"', b'<factura xmlns="urn:x" id="comprobante"'
    )
    assert invoices.parse(namespaced).total == TOTAL


def test_parse_refusals() -> None:
    with pytest.raises(invoices.NotAnInvoice):
        invoices.parse(factura(cod="04"))
    with pytest.raises(invoices.NotAnInvoice):
        invoices.parse(factura(cod="04", wrapped=False))
    with pytest.raises(invoices.InvoiceError, match="isn't an electronic invoice"):
        invoices.parse(b"%PDF-1.4 not xml")
    with pytest.raises(invoices.InvoiceError, match="isn't an SRI electronic invoice"):
        invoices.parse(b"<root><x/></root>")
    with pytest.raises(invoices.InvoiceError, match="access key"):
        invoices.parse(factura(key="123"))
    with pytest.raises(invoices.InvoiceError, match="date"):
        invoices.parse(factura(day="2026-10-28"))
    with pytest.raises(invoices.InvoiceError, match=r"add up to 15.00 but the invoice says 16.00"):
        invoices.parse(factura(subtotal_delta="1"))
    with pytest.raises(invoices.InvoiceError, match="no product lines"):
        invoices.parse(
            factura(wrapped=False).replace(b"<detalles>", b"<x>").replace(b"</detalles>", b"</x>")
        )
    with pytest.raises(invoices.InvoiceError, match="infoTributaria"):
        invoices.parse(b"<factura><detalles/></factura>")
    with pytest.raises(invoices.InvoiceError) as big:
        invoices.parse(b"<" + b"x" * invoices.MAX_BYTES)
    assert big.value.status == 413
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
        b"<factura>&b;</factura>"
    )
    with pytest.raises(invoices.InvoiceError):
        invoices.parse(bomb)  # entities are refused, not expanded


def test_product_keys_and_keywords() -> None:
    assert invoices.product_key("  Leche  entera Vita 1L ") == "LECHE ENTERA VITA 1L"
    assert invoices.product_key("Pañales Bebé") == "PANALES BEBE"
    cases = {
        "LECHE ENTERA 1L": "Dairy & Eggs",
        "CHOCOLATE CON LECHE": "Snacks & Sweets",
        "PANALES PEQUENOS": "Baby",
        "PAN BLANCO": "Bakery",
        "PANELA": None,
        "PAPEL HIGIENICO 12U": "Household & Cleaning",
        "YOG TONI FRUT 1L": None,
    }
    assert {k: invoices.keyword_group(k) for k in cases} == cases


# ---------------------------------------------------------------- storing, matching, groups
def test_upload_matches_and_groups(client: TestClient, db: Session) -> None:
    paid = card_line(db, date(2026, 10, 29), TOTAL)  # posted the next day
    out = upload(client, ("a.xml", factura()))
    assert out[0]["outcome"] == "stored", out
    assert out[0]["message"] == "SUPER PRUEBA: 4 products, 15.98; matched to its payment."
    inv = db.get(Invoice, out[0]["invoice_id"])
    assert inv is not None and inv.transaction_id == paid.transaction_id
    assert inv.received_by == "hernan@example.com"
    groups = {ln.description: (ln.product_group, ln.group_source) for ln in inv.lines}
    assert groups["LECHE ENTERA 1L"] == ("Dairy & Eggs", "keyword")
    assert groups["YOG TONI FRUT 1L"] == (None, None)
    log = db.scalars(select(LoadLog).where(LoadLog.source == "invoice")).one()
    assert log.rows_loaded == 4

    again = upload(client, ("b.xml", factura()), ("c.xml", factura(cod="04")), ("d.txt", b"x"))
    assert [o["outcome"] for o in again] == ["duplicate", "skipped", "rejected"]
    assert again[0]["message"] == "Invoice 072-140-000123456 is already in the app."
    assert db.scalar(select(func.count()).select_from(Invoice)) == 1


def test_payment_loaded_later_and_ambiguous(client: TestClient, db: Session) -> None:
    out = upload(client, ("a.xml", factura()))
    assert out[0]["message"].endswith("its payment isn't loaded yet.")
    # Too early (two days before) and too late (five days after) don't count.
    card_line(db, date(2026, 10, 26), TOTAL)
    card_line(db, date(2026, 11, 2), TOTAL)
    assert invoices.link_pending(db) == 0
    card_line(db, date(2026, 10, 28), TOTAL)
    assert invoices.link_pending(db) == 1
    # Two purchases for the same amount that day: nobody guesses.
    other = factura(key=OTHER_KEY, day="15/10/2026")
    card_line(db, date(2026, 10, 15), TOTAL, n=1)
    card_line(db, date(2026, 10, 16), TOTAL, n=2)
    upload(client, ("b.xml", other))
    inv = db.scalar(select(Invoice).where(Invoice.access_key == OTHER_KEY))
    assert inv is not None and inv.transaction_id is None


def test_purchases_month_and_groups(client: TestClient, db: Session) -> None:
    card_line(db, date(2026, 10, 28), TOTAL)
    upload(client, ("a.xml", factura()))
    p = client.get("/api/invoices", params={"month": "2026-10"}).json()
    assert (Decimal(p["total"]), Decimal(p["matched_total"])) == (TOTAL, TOTAL)
    assert p["invoices"][0]["paid_with"]["account"] == "Capital One Venture"
    totals = {g["group"]: Decimal(g["amount"]) for g in p["groups"]}
    assert totals == {
        "Household & Cleaning": Decimal("7.48"),
        "Meat & Fish": Decimal("4.00"),
        "Not grouped yet": Decimal("2.40"),
        "Dairy & Eggs": Decimal("2.10"),
    }
    # Keyword groups wait for a person too; the yogurt has none.
    to_group = {u["description"]: u["suggested_group"] for u in p["to_group"]}
    assert to_group["YOG TONI FRUT 1L"] is None and to_group["LECHE ENTERA 1L"] == "Dairy & Eggs"
    assert "Baby" in p["product_groups"] and p["suggestions_available"] is False

    # A person's group becomes a rule for this and every later invoice.
    put = client.put(
        "/api/invoices/products",
        json={"product_key": "YOG TONI FRUT 1L", "product_group": "Dairy & Eggs"},
        headers=USER,
    )
    assert put.status_code == 200 and put.json()["lines_updated"] == 1
    rule = db.scalars(select(ProductRule)).one()
    assert (rule.product_group, rule.created_by) == ("Dairy & Eggs", "hernan@example.com")
    upload(client, ("b.xml", factura(key=OTHER_KEY, day="02/11/2026")))
    nov = db.scalar(select(Invoice).where(Invoice.access_key == OTHER_KEY))
    assert nov is not None
    yog = next(ln for ln in nov.lines if ln.description == "YOG TONI FRUT 1L")
    assert (yog.product_group, yog.group_source) == ("Dairy & Eggs", "rule")
    # Confirming again updates the rule.
    client.put(
        "/api/invoices/products",
        json={"product_key": "YOG TONI FRUT 1L", "product_group": "Snacks & Sweets"},
    )
    db.expire_all()
    assert db.scalars(select(ProductRule)).one().product_group == "Snacks & Sweets"

    bad = client.put("/api/invoices/products", json={"product_key": "X", "product_group": "Nope"})
    assert bad.status_code == 422
    assert client.get("/api/invoices", params={"month": "Oct"}).status_code == 422
    empty = client.get("/api/invoices", params={"month": "2020-01"}).json()
    assert empty["invoices"] == [] and Decimal(empty["total"]) == 0


def test_claude_suggestions(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(client, ("a.xml", factura()))
    assert client.post("/api/invoices/suggest", params={"month": "2026-10"}).status_code == 503
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    get_settings.cache_clear()
    sent: list[dict[str, str]] = []

    def fake(products: dict[str, str]) -> dict[str, str]:
        sent.append(products)
        return {pid: "Dairy & Eggs" for pid, d in products.items() if d.startswith("YOG")}

    monkeypatch.setattr(product_suggest, "call_claude", fake)
    try:
        resp = client.post("/api/invoices/suggest", params={"month": "2026-10"})
        assert resp.status_code == 200 and resp.json() == {"products": 1}
        assert list(sent[0].values()) == ["YOG TONI FRUT 1L"]  # descriptions only
        yog = db.scalars(
            select(InvoiceLine).where(InvoiceLine.description == "YOG TONI FRUT 1L")
        ).one()
        assert (yog.product_group, yog.group_source) == ("Dairy & Eggs", "claude")
        # Nothing left to ask about.
        assert client.post("/api/invoices/suggest", params={"month": "2026-10"}).json() == {
            "products": 0
        }

        def broken(products: dict[str, str]) -> dict[str, str]:
            raise product_suggest.SuggestError("Claude could not be reached: APIError.")

        monkeypatch.setattr(product_suggest, "call_claude", broken)
        db.execute(InvoiceLine.__table__.update().values(product_group=None, group_source=None))
        db.commit()
        assert client.post("/api/invoices/suggest", params={"month": "2026-10"}).status_code == 502
    finally:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        get_settings.cache_clear()


# ---------------------------------------------------------------- Gmail and Claude
@pytest.fixture
def inbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    monkeypatch.setenv("INBOX_TOKEN", "i" * 64)
    get_settings.cache_clear()
    yield {"Authorization": f"Bearer {'i' * 64}"}
    monkeypatch.delenv("INBOX_TOKEN")
    get_settings.cache_clear()


def test_invoices_by_email(inbox: dict[str, str], client: TestClient, db: Session) -> None:
    def post(name: str, data: bytes) -> dict:  # type: ignore[type-arg]
        resp = client.post(
            "/api/inbox",
            files={"file": (name, data, "application/octet-stream")},
            data={"sender": "infoedoc@vendor.example"},
            headers=inbox,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()  # type: ignore[no-any-return]

    got = post("0210.xml", factura())
    assert (got["status"], got["outcome"], got["statement_id"]) == ("read", "stored", None)
    inv = db.get(Invoice, got["invoice_id"])
    assert inv is not None and inv.received_by == "gmail (infoedoc@vendor.example)"
    assert post("again", factura())["status"] == "duplicate"  # no .xml name: sniffed
    assert post("nc.xml", factura(cod="04"))["status"] == "skipped"
    assert post("bad.xml", b"<x/>")["status"] == "rejected"


def test_claude_reads_purchases(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_server, "get_reader_engine", lambda: engine)
    upload(client, ("a.xml", factura()))
    upload(client, ("b.xml", factura(key=OTHER_KEY, day="30/10/2026")))
    got = mcp_server.purchases("2026-10", top=2)
    assert (got["invoices"], got["total"]) == (2, "31.96")
    assert got["by_group"][0] == {"group": "Household & Cleaning", "amount": "14.96", "lines": 2}
    assert got["top_products"][0] == {
        "product": "DETERGENTE POLVO 2KG",
        "group": "Household & Cleaning",
        "quantity": "2",
        "amount": "14.96",
    }
    assert len(got["top_products"]) == 2
    assert got["vendors"] == [{"vendor": "SUPER PRUEBA", "invoices": 2, "amount": "31.96"}]


def test_call_claude_sends_descriptions_and_reads_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from types import SimpleNamespace
    from typing import Any

    import anthropic

    calls: list[dict[str, Any]] = []
    state = {"stop": "end_turn", "text": '{"groups": [{"product_id": "p1", "group_id": "g2"}]}'}

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason=state["stop"],
                content=[SimpleNamespace(type="text", text=state["text"])],
            )

    class FakeClient:
        def __init__(self, **_kw: Any) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    assert product_suggest.call_claude({"p1": "YOG TONI 1L"}) == {"p1": "Dairy & Eggs"}
    sent = json.loads(calls[0]["messages"][0]["content"])
    assert sent["products"] == [{"id": "p1", "description": "YOG TONI 1L"}]
    assert set(sent) == {"groups", "products"}  # nothing about the vendor, amounts or people
    schema = calls[0]["output_config"]["format"]["schema"]
    assert schema["properties"]["groups"]["items"]["properties"]["product_id"]["enum"] == ["p1"]

    state["stop"] = "max_tokens"
    with pytest.raises(product_suggest.SuggestError, match="cut off"):
        product_suggest.call_claude({"p1": "X"})
    state["stop"], state["text"] = "end_turn", "nope"
    with pytest.raises(product_suggest.SuggestError, match="could not be read"):
        product_suggest.call_claude({"p1": "X"})

    class Failing(FakeMessages):
        def create(self, **kwargs: Any) -> Any:
            raise anthropic.APIConnectionError(request=SimpleNamespace())  # type: ignore[arg-type]

    class FailingClient(FakeClient):
        def __init__(self, **_kw: Any) -> None:
            self.messages = Failing()

    monkeypatch.setattr(anthropic, "Anthropic", FailingClient)
    with pytest.raises(product_suggest.SuggestError, match="could not be reached"):
        product_suggest.call_claude({"p1": "X"})
