"""Golden test on a synthetic Produbanco Visa statement with the real layout (made-up values)."""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.detect import detect, read_pages
from app.ingestion.parsers import PARSERS, produbanco_card
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import PRODU_CARD_LINES, produbanco, produbanco_card_full


def test_detected_as_the_card_with_its_own_digits() -> None:
    found = detect("\n".join(read_pages(produbanco_card_full())))
    # The card's "CUENTA: … No. CC" is not a savings account: only 5997 is kept.
    assert (found.source, found.kind, found.last4) == ("produbanco", "card", ["5997"])
    assert (found.period_start, found.period_end) == (date(2026, 7, 1), date(2026, 7, 31))
    savings = detect("\n".join(read_pages(produbanco())))
    assert (savings.kind, savings.last4) == ("bank", ["3721"])


def test_statement_ties_out() -> None:
    p = PARSERS["produbanco"](read_pages(produbanco_card_full()))
    assert p.parser == "produbanco_card"
    assert p.tieout_ok, [c for c in p.checks if not c.ok]
    assert (p.opening_balance, p.closing_balance) == (Decimal("40.24"), Decimal("149.94"))
    by = {ln.description: ln for ln in p.lines}
    internet = by["PROVEEDOR DE INTERNET"]  # "EC 840" (country, currency) dropped
    assert (internet.txn_date, internet.amount, internet.section, internet.person) == (
        date(2026, 7, 1),
        Decimal("-40.24"),
        "purchase",
        "Hernan",
    )
    assert by["TIENDA EN LINEA"].amount == Decimal("-25.00")  # the dollar amount, not M.E.
    assert by["DEVOLUCION TIENDA EN LINEA"].amount == Decimal("5.00")  # "-": money back
    assert by["PROGRAMA DE PREMIOS"].section == "fee"
    pay = by["*** SU PAGO - MUCHAS GRACIAS ***"]
    assert (pay.section, pay.amount) == ("payment", Decimal("40.24"))


def test_a_skipped_line_is_caught() -> None:
    lines = [ln for ln in PRODU_CARD_LINES if "TARIFA" not in ln]
    p = PARSERS["produbanco"](read_pages(produbanco_card_full(lines=lines)))
    assert not p.tieout_ok
    assert "Charges (TOTAL CARGOS)" in [c.name for c in p.checks if not c.ok]


def test_unreadable_lines_are_rejected() -> None:
    lines = [
        *PRODU_CARD_LINES,
        "07/20/2026 1 ALGO RARO XYZ 1.00 +",
        "07/21/2026 1 SIN SIGNO CONS. 1.00",
    ]
    p = PARSERS["produbanco"](read_pages(produbanco_card_full(lines=lines)))
    reasons = sorted(r.reason for r in p.rejects)
    assert reasons == [
        "Line could not be read: amount or sign not readable",
        "Line could not be read: operation not recognized",
    ]
    assert not p.tieout_ok


def test_wrong_layout() -> None:
    with pytest.raises(ParseError, match="Period"):
        produbanco_card.parse(["TARJETA No.:1 Resumen de movimientos"])
    with pytest.raises(ParseError, match="Summary"):
        produbanco_card.parse(["Periodo : 07/01/2026 - 07/31/2026"])


def test_uploaded_card_goes_to_the_visa_and_savings_stay_apart(client) -> None:  # type: ignore[no-untyped-def]
    files = [
        ("files", ("4009XXXXXXXX5997.pdf", produbanco_card_full(), "application/pdf")),
        ("files", ("savings.pdf", produbanco(), "application/pdf")),
    ]
    out = {
        r["statement"]["file_name"]: r["statement"]
        for r in client.post("/api/statements", files=files).json()
    }
    card = out["4009XXXXXXXX5997.pdf"]
    assert [a["name"] for a in card["accounts"]] == ["Produbanco Visa"]
    assert card["account_match"] == "last4"
    assert [a["name"] for a in out["savings.pdf"]["accounts"]] == ["Produbanco Ahorros Hernan"]
    batch = client.post(f"/api/statements/{card['statement_file_id']}/read").json()
    assert batch["tieout_ok"], batch["checks"]
    internet = next(ln for ln in batch["lines"] if ln["description"] == "PROVEEDOR DE INTERNET")
    assert internet["type"] == "expense"


def test_seed_v6_keeps_an_account_added_by_hand(db) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import func, select

    from app.models import Account, Category, MerchantRule
    from app.seeds import load_v6

    load_v6(db.connection(), Account.__table__, Category.__table__, MerchantRule.__table__)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Account).where(Account.last4 == "5997")) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(MerchantRule)
            .where(MerchantRule.pattern == "MEGADATOS")
        )
        == 1
    )
