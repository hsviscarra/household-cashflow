"""Golden test on a synthetic Diners Club statement with the real layout."""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.detect import detect, read_pages, read_pdf
from app.ingestion.parsers import diners
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import diners_full


def test_statement_ties_out_with_main_and_additional_card() -> None:
    p = diners.parse(read_pages(diners_full()))
    assert (p.period_start, p.period_end) == (date(2026, 6, 4), date(2026, 7, 3))
    assert p.tieout_ok and not p.rejects, [c for c in p.checks if not c.ok]
    names = {c.name for c in p.checks}
    assert {
        "Card •••• 1234 subtotal",
        "Card •••• 5678 subtotal",
        "Hernan's purchases (Resumen por cliente)",
        "Lauren's purchases (Resumen por cliente)",
        "Remaining balance of deferred purchases",
    } <= names
    # The foreign-purchases summary repeats AWS; it is read once.
    assert [ln.description for ln in p.lines].count("DN AMAZON WEB SERVICES") == 1

    by_desc = {ln.description: ln for ln in p.lines}
    school = by_desc["COLEGIO DE PRUEBA CUMBAYA"]
    # An installment of a November purchase is billed on the closing date.
    assert (school.amount, school.reference, school.txn_date) == (
        Decimal("-300.00"),
        "8/12",
        date(2026, 7, 3),
    )
    assert by_desc["LAVANDERIA DE PRUEBA"].amount == Decimal("-1038.59")  # thousands separator
    assert (by_desc["SUPERMAXI CUMBAYA"].cardholder, by_desc["SUPERMAXI CUMBAYA"].person) == (
        "5678",
        "Lauren",
    )
    sections = {d: ln.section for d, ln in by_desc.items()}
    assert sections['SU PAGO "MUCHAS GRACIAS"'] == "payment"
    assert sections["GASTO GESTION COBRANZAS"] == "fee"
    assert sections["INTERESES DE MORA"] == sections["INT. FINANCIAMIENTO"] == "interest"
    assert sections["CONT_FIN_SOLCA_C.ROT**"] == "charge"
    assert by_desc['SU PAGO "MUCHAS GRACIAS"'].amount == Decimal("650.00")


def test_a_purchase_with_iva_counts_value_plus_iva() -> None:
    """A gas station fee prints VALOR 0,20 and IVA 0,03: it costs 0,23 (it used to be read as
    0,20 with a "deferred balance" of 0,03, leaving the card 3 cents short)."""
    p = diners.parse(read_pages(diners_full(with_iva=True)))
    assert p.tieout_ok, [(c.name, c.expected, c.actual) for c in p.checks if not c.ok]
    fee = next(ln for ln in p.lines if ln.description == "TARIFA CONSUMO GASOLINERA")
    assert fee.amount == Decimal("-0.23")
    # The installment's remaining balance still goes to deferred, not to the charge.
    deferred = next(c for c in p.checks if c.name.startswith("Remaining balance"))
    assert deferred.ok


def test_purchases_with_grace_months_wait_for_their_statement() -> None:
    """Purchases with grace months are listed with their first installment and billing date;
    they are billed later, so they aren't this statement's lines (they were, 2026-11-09)."""
    p = diners.parse(read_pages(diners_full(with_grace=True)))
    assert p.tieout_ok, [(c.name, c.expected, c.actual) for c in p.checks if not c.ok]
    assert not any("PENSION" in ln.description or "LIBRERIA" in ln.description for ln in p.lines)


def test_wrong_card_subtotal_fails() -> None:
    p = diners.parse(read_pages(diners_full(subtotal_delta="1")))
    assert [c.name for c in p.checks if not c.ok] == ["Card •••• 1234 subtotal"]


def test_detection_names_the_main_cardholder() -> None:
    found = detect(read_pdf(diners_full()).text)
    assert (found.source, found.owner) == ("diners", "Hernan")
    assert found.last4 == ["1234", "5678"]


def test_wrong_layout_and_bad_lines() -> None:
    with pytest.raises(ParseError, match="Period"):
        diners.parse(["nothing"])
    with pytest.raises(ParseError, match="Period could not be read"):
        diners.parse(["04 XYZ 2026 AL 03 JUL 2026"])
    with pytest.raises(ParseError, match="SALDO ANTERIOR"):
        diners.parse(["04 JUN 2026 AL 03 JUL 2026"])
    head = (
        "04 JUN 2026 AL 03 JUL 2026\nSALDO ANTERIOR: 0,00\nPAGOS/CRÉDITOS: 0,00\n"
        "CONSUMOS: 1,00\nDÉBITOS: 0,00\nTotal a pagar: 1,00\n"
    )
    p = diners.parse(
        [head + "Consumo período actual\n30/02 1 FECHA IMPOSIBLE 1,00\n01/07 TEXTO SIN VALOR"]
    )
    assert len(p.rejects) == 2 and not p.tieout_ok
