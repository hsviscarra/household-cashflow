"""Pacificard: the parser on OCR-like text (noise included), and OCR on a synthetic screenshot."""

from datetime import date
from decimal import Decimal
from functools import cache

import pytest

from app.ingestion import ocr
from app.ingestion.parsers import pacificard
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import pacificard_full

# What OCR returns for a real statement, with its usual noise (made-up values).
NOISY = """Periodo de corte desde: 25/AGO/2026 hasta 24/SEP/2026
400.00 148.85 80.00 4.10 472.95
j Deuda Total 472.95 100% 472.95
s44444 32LDO ANTERIOR 400.00
0000000001 PRUEBA HERNAN TITULAR
4GO/ 28 100001 SEG. DESGRAVAMEN SALDO QUITO CONS3 3.65 +
SEP/08 100002 SU PAGO PAGO DIRECTO BDP GUAYAQUI PAGO 80.00 -
SEP/24 200001 CARGOS CAPITAL ANTERIOR Int 4.10 +
SEP/24 100003 CONTRIB. FINANC.SOLCA ROT. (0.50%) cons 0.21 +
0000000002 PRUEBA ADICIONAL LAUREW
SEP/07 100004 SERV. RENOVACION TARJ/CHIP CONS 5.03 +
000000000001 HERWAN PRUEBA TITULAR
SEP/0S 100005 SERVICIO DE PRUEBA REF123 BILL.I CONS 120.00 120.00 +
SEP/05 100005 W/D COMISION CONSUMO EXT I BILL.I N/D- 1.96 +
SEP/05 100005 N/D IVA SERVICIO DIGITAL BILL.I N/D 18.00 +
TOTAL PAGO DE CONTADO 672.95
SALDO ACTUAL ROTATIVO 472.95
SALDO ACTUAL DIFERIDO 0.00
SUBTOTAL CONSUMOS PERIODS 148.85
SUBTOTAL PAGOS/CREDITOS 80.00"""


def test_noisy_text_ties_out() -> None:
    p = pacificard.parse([NOISY])
    assert (p.period_start, p.period_end) == (date(2026, 8, 25), date(2026, 9, 24))
    assert p.tieout_ok and not p.rejects, [c for c in p.checks if not c.ok]
    # One misread printing of the total (672.95) is outvoted by the others.
    assert (p.opening_balance, p.closing_balance) == (Decimal("400.00"), Decimal("472.95"))
    first = p.lines[0]
    assert (first.txn_date, first.section, first.amount) == (
        date(2026, 8, 28),
        "charge",
        Decimal("-3.65"),
    )
    by_desc = {ln.description: ln for ln in p.lines}
    assert by_desc["SU PAGO PAGO DIRECTO BDP GUAYAQUI"].amount == Decimal("80.00")
    assert by_desc["CARGOS CAPITAL ANTERIOR"].section == "interest"
    assert by_desc["SERV. RENOVACION TARJ/CHIP"].person == "Lauren"  # "LAUREW"
    assert by_desc["SERV. RENOVACION TARJ/CHIP"].section == "fee"
    abroad = by_desc["SERVICIO DE PRUEBA REF123 BILL.I"]
    assert (abroad.txn_date, abroad.amount, abroad.person) == (
        date(2026, 9, 5),  # "SEP/0S"
        Decimal("-120.00"),
        "Hernan",  # "HERWAN"
    )
    assert by_desc["N/D COMISION CONSUMO EXT I BILL.I"].section == "fee"  # "W/D" read as N/D
    assert by_desc["N/D IVA SERVICIO DIGITAL BILL.I"].section == "charge"


def test_unreadable_end_date_uses_the_cut_off_and_spaced_slashes() -> None:
    """October 2026 read "hasta 2VOCT/2026" (end unreadable, so "Fecha de corte: 23/O0CT/2026"
    is used) and "OCT /23 … SOLCA" with a space before the slash, which was skipped (0.29 short)."""
    text = NOISY.replace("hasta 24/SEP/2026", "hasta 2VSEP/2026\n. Fecha de corte: 24/S3EP/2026")
    text = text.replace("SEP/24 100003 CONTRIB", "SEP /24 100003 CONTRIB")
    p = pacificard.parse([text])
    assert (p.period_start, p.period_end) == (date(2026, 8, 25), date(2026, 9, 24))
    assert p.tieout_ok and not p.rejects, [c for c in p.checks if not c.ok]
    solca = next(ln for ln in p.lines if "SOLCA" in ln.description)
    assert solca.amount == Decimal("-0.21")
    assert pacificard._period_date("23/O0CT/2026") == date(2026, 10, 23)


def test_a_misread_amount_is_caught() -> None:
    p = pacificard.parse([NOISY.replace("cons 0.21 +", "cons 6.21 +")])
    assert not p.tieout_ok
    assert "Purchases and debits (SUBTOTAL CONSUMOS)" in [c.name for c in p.checks if not c.ok]


def test_an_unreadable_digit_is_filled_from_the_printed_subtotal() -> None:
    """April 2026 read "INT €.04 +" for 6.04 of interest: rejected, so charges were 6.04 short.
    The one unreadable amount in a group takes the subtotal's remainder when it fits the shape."""
    p = pacificard.parse(
        [NOISY.replace("Int 4.10 +", "Int €.10 +").replace("cons 0.21", "cons §.21")]
    )
    assert p.tieout_ok and not p.rejects, [c for c in p.checks if not c.ok]
    by_desc = {ln.description: ln for ln in p.lines}
    assert by_desc["CARGOS CAPITAL ANTERIOR"].amount == Decimal("-4.10")
    assert [ln.line_no for ln in p.lines] == sorted(ln.line_no for ln in p.lines)


def test_an_unreadable_amount_that_does_not_fit_stays_rejected() -> None:
    # Two characters can't be one digit (4.10 doesn't fit "€€.10"), and two unreadable lines in
    # one group can't share a remainder: both stay rejected and the statement doesn't tie out.
    for text in (
        NOISY.replace("Int 4.10 +", "Int €€.10 +"),
        NOISY.replace("Int 4.10 +", "Int €.10 +")
        .replace("cons 0.21", "cons §.21")
        .replace("CONS 5.03", "CONS €.03"),
    ):
        p = pacificard.parse([text])
        assert not p.tieout_ok and p.rejects
        assert all("amount not readable" in r.reason for r in p.rejects)


def test_unreadable_start_date_and_bad_lines() -> None:
    text = NOISY.replace("desde: 25/AGO/2026", "desde: 2AGO/2026").replace(
        "SEP/07 100004", "SEP/3S 100004"
    )
    text += "\nOCT/99 1 ALGO CONS 1.00 +"
    text += "\nSEP/01 1 SIN OPERACION XYZ 1.00 +\nSEP/01 1 SIN SIGNO CONS 1.00"
    p = pacificard.parse([text])
    assert p.period_start == date(2026, 8, 25)  # the day after the same day a month earlier
    reasons = [r.reason for r in p.rejects]
    assert len(reasons) == 4 and not p.tieout_ok
    assert any("operation 'XYZ'" in r for r in reasons)


def test_missing_period_or_totals() -> None:
    with pytest.raises(ParseError, match="Period"):
        pacificard.parse(["nothing"])
    with pytest.raises(ParseError, match="Previous balance"):
        pacificard.parse(["Periodo de corte desde: 25/AGO/2026 hasta 24/SEP/2026"])


def test_deferred_balance_stops_the_load() -> None:
    p = pacificard.parse(
        [NOISY.replace("SALDO ACTUAL DIFERIDO 0.00", "SALDO ACTUAL DIFERIDO 120.00")]
    )
    assert [c.name for c in p.checks if not c.ok] == ["Deferred balance (none expected)"]


needs_ocr = pytest.mark.skipif(not ocr.available(), reason="tesseract is not installed")


@cache
def _ocr_fixture() -> tuple[str, ...]:
    return tuple(ocr.ocr_pages(pacificard_full(), ocr.first_page))


@needs_ocr
def test_ocr_reads_the_synthetic_screenshot() -> None:
    p = pacificard.parse(list(_ocr_fixture()))
    assert p.tieout_ok and not p.rejects, ([c for c in p.checks if not c.ok], p.rejects)
    assert (p.opening_balance, p.closing_balance) == (Decimal("500.00"), Decimal("526.53"))
    assert len(p.lines) == 9
    assert {ln.person for ln in p.lines} == {"Hernan", "Lauren"}
    assert "CONCEPTOS" not in _ocr_fixture()[0]  # the fine print below the banner isn't read


@needs_ocr
def test_ocr_header_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "banco del pacifico s.a." in ocr.header_text(pacificard_full()).lower()
    from tests.fixtures.statements import capitalone_full

    assert ocr.header_text(capitalone_full()) == ""  # a text PDF has no page pictures
    with pytest.raises(ocr.OcrError, match="no page images"):
        ocr.ocr_pages(capitalone_full())

    def missing(*_a: object, **_k: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(ocr.subprocess, "run", missing)
    with pytest.raises(ocr.OcrError, match="not installed"):
        ocr.header_text(pacificard_full())
