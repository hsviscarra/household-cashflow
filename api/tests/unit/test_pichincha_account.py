"""F19: Banco Pichincha bank account statements: detection (an account, not the card), the
parser's tie-out, and reading one through the app into the right account."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.detect import detect, read_pages, read_pdf
from app.ingestion.parsers import PARSERS, pichincha_account
from app.ingestion.parsers.base import ParseError
from app.models import Account
from tests.fixtures import statements as s

PDF = "application/pdf"
USER = {"X-MS-CLIENT-PRINCIPAL-NAME": "Hernan@Example.com"}


def test_detects_an_account_not_the_card() -> None:
    d = detect(read_pdf(s.pichincha_account_full()).text)
    assert (d.source, d.last4, d.kind) == ("pichincha", ["0001"], "bank")
    assert (d.period_start.isoformat(), d.period_end.isoformat()) == (  # type: ignore[union-attr]
        "2026-08-08",
        "2026-09-04",
    )
    card = detect(read_pdf(s.pichincha()).text)
    assert (card.kind, card.last4) == ("card", ["2829"])


def test_parses_and_ties_out() -> None:
    st = PARSERS["pichincha"](read_pages(s.pichincha_account_full()))
    assert st.tieout_ok and not st.rejects
    assert (st.opening_balance, st.closing_balance) == (Decimal("40.00"), Decimal("1089.59"))
    assert [ln.amount for ln in st.lines] == [
        Decimal("-50.00"),
        Decimal("100.00"),
        Decimal("-0.36"),
        Decimal("-0.05"),
        Decimal("1000.00"),
    ]
    assert [ln.section for ln in st.lines][2:4] == ["fee", "fee"]
    assert st.lines[0].txn_date.isoformat() == "2026-08-13"
    assert st.lines[-1].description == "DEPOSITO"
    assert {c.name for c in st.checks} >= {"Number of debits", "Credits add up to the summary"}


def test_english_month_names_across_the_new_year() -> None:
    """The January 2026 statement printed "09-Dec" and "05-Jan" (every line was rejected as an
    unknown month): English abbreviations read the same, and December falls in the year before."""
    pages = read_pages(s.pichincha_account_full())
    english = [
        p.replace(
            "FECHA ÚLTIMO CORTE (FACTURA) 07-08-2026", "FECHA ÚLTIMO CORTE (FACTURA) 06-12-2025"
        )
        .replace("FECHA ESTE CORTE 04-09-2026", "FECHA ESTE CORTE 09-01-2026")
        .replace("13-ago.", "09-Dec")
        .replace("18-ago.", "11-Dec")
        .replace("19-ago.", "31-Dec")
        .replace("03-sep.", "05-Jan")
        for p in pages
    ]
    st = PARSERS["pichincha"](english)
    assert st.tieout_ok and not st.rejects, [r.reason for r in st.rejects]
    assert [ln.txn_date.isoformat() for ln in st.lines] == [
        "2025-12-09",
        "2025-12-11",
        "2025-12-31",
        "2025-12-31",
        "2026-01-05",
    ]
    assert pichincha_account.MONTHS["aug"] == pichincha_account.MONTHS["ago"] == 8


def test_a_wrong_count_or_balance_blocks() -> None:
    bad = PARSERS["pichincha"](read_pages(s.pichincha_account_full(credit_count=3)))
    assert not bad.tieout_ok
    assert [c.name for c in bad.checks if not c.ok] == ["Number of credits"]
    with pytest.raises(ParseError, match="FECHA ESTE CORTE"):
        pichincha_account.parse(["CHEQUES / DEBITOS (1) 1.00"])
    with pytest.raises(ParseError, match="SALDO ANTERIOR"):
        pichincha_account.parse(["FECHA ESTE CORTE 04-09-2026", "CHEQUES / DEBITOS (1) 1.00"])
    odd = pichincha_account.parse(
        [
            "FECHA ESTE CORTE 04-09-2026 SALDO ANTERIOR 1.00 SALDO ACTUAL 1.00",
            "13-xyz. 12 1 SOMETHING 1.00 0.00 0.00",
            "31-feb. 12 1 SOMETHING 1.00 0.00 0.00",
            "garbled line 1.00 0.00 0.00",
        ]
    )
    assert odd.rejects[0].reason == "Unknown month"
    assert len(odd.rejects) == 3 and odd.period_start.isoformat() == "2026-09-01"


def test_read_into_the_account_never_the_card(client: TestClient, db: Session) -> None:
    files = [("files", ("cta.pdf", s.pichincha_account_full(), PDF))]
    up = client.post("/api/statements", files=files, headers=USER).json()[0]["statement"]
    # Only the card is at Banco Pichincha: the account statement must not land on it.
    assert up["status"] == "needs_account" and up["accounts"] == []
    db.add(
        Account(
            name="Pichincha Ahorros",
            institution="Banco Pichincha",
            kind="savings",
            owner="Hernan",
            country="EC",
            last4="0001",
        )
    )
    db.commit()
    files = [("files", ("cta2.pdf", s.pichincha_account_full(opening="10.00"), PDF))]
    up = client.post("/api/statements", files=files, headers=USER).json()[0]["statement"]
    assert [a["name"] for a in up["accounts"]] == ["Pichincha Ahorros"]
    assert up["account_match"] == "last4"
    b = client.post(f"/api/statements/{up['statement_file_id']}/read").json()
    assert b["tieout_ok"], b["checks"]
    assert client.post(f"/api/batches/{b['batch_id']}/approve", headers=USER).status_code == 200
    acct = db.scalar(select(Account).where(Account.name == "Pichincha Ahorros"))
    assert acct is not None
