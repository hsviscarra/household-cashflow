"""Golden test on a synthetic Banco Pichincha statement with the real layout."""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.detect import read_pages
from app.ingestion.parsers import pichincha
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import pichincha_full


def test_statement_ties_out_with_both_cards() -> None:
    p = pichincha.parse(read_pages(pichincha_full()))
    assert (p.period_start, p.period_end) == (date(2026, 6, 13), date(2026, 7, 12))
    assert p.opening_balance == Decimal("400.00")
    assert p.tieout_ok and not p.rejects
    names = [c.name for c in p.checks]
    assert {"Card •••• 6331 subtotal", "Card •••• 2829 subtotal"} <= set(names)

    pay = p.lines[0]
    assert (pay.section, pay.amount, pay.cardholder) == ("payment", Decimal("300.00"), None)
    sections = {ln.description: ln.section for ln in p.lines}
    assert sections["INTERESES SALDO A FAVOR"] == "interest"
    assert sections["INT. FINANCIAMIENTO"] == "interest"
    assert sections["CONT_FIN_SOLCA_C.ROT**"] == "charge"
    assert sections["RET IVA SERV DIGITAL 100%"] == "charge"
    uber = next(ln for ln in p.lines if ln.description.startswith("UBER"))
    assert (uber.amount, uber.cardholder, uber.person) == (Decimal("-3.99"), "6331", "Hernan")
    assert uber.description == "UBER *ONE MEMBERSHIP U V"  # operation and country code removed
    big = next(ln for ln in p.lines if ln.description.startswith("CONECEL"))
    assert big.amount == Decimal("-1024.14")  # Ecuadorian thousands separator


def test_deferred_purchase_keeps_installment_and_balance() -> None:
    p = pichincha.parse(read_pages(pichincha_full()))
    dif = next(ln for ln in p.lines if ln.description.startswith("TIENDA"))
    assert (dif.amount, dif.reference) == (Decimal("-50.00"), "2/6")
    assert Decimal("200.00") in p.totals.values()


def test_wrong_card_subtotal_fails() -> None:
    p = pichincha.parse(read_pages(pichincha_full(subtotal_delta="1")))
    assert [c.name for c in p.checks if not c.ok] == ["Card •••• 6331 subtotal"]


@pytest.mark.parametrize(
    ("text", "value"),
    [("1.057,78", "1057.78"), ("1,057.81-", "-1057.81"), ("310,00-", "-310.00"), ("0,03", "0.03")],
)
def test_amount_formats(text: str, value: str) -> None:
    assert pichincha.amount(text) == Decimal(value)


def test_wrong_layout_and_bad_dates() -> None:
    with pytest.raises(ParseError, match="Period"):
        pichincha.parse(["nothing"])
    with pytest.raises(ParseError, match="Summary"):
        pichincha.parse(["13/06/2026 12/07/2026"])
    p = pichincha.parse(
        [
            "13/06/2026 12/07/2026\nMOVIMIENTO 0.00 0.00 1.00 1.00",
            "DETALLE DE MOVIMIENTOS\n01/01 123 FUERA DE PERIODO CONSUMO 1,00",
        ]
    )
    assert p.rejects and not p.tieout_ok
