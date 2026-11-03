"""Golden test on a synthetic Produbanco savings statement with the real layout."""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.detect import read_pages
from app.ingestion.parsers import produbanco
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import produbanco_full


def test_statement_ties_out_line_by_line() -> None:
    p = produbanco.parse(read_pages(produbanco_full()))
    assert (p.period_start, p.period_end) == (date(2026, 7, 1), date(2026, 7, 31))
    assert (p.opening_balance, p.closing_balance) == (Decimal("1500.00"), Decimal("243.40"))
    assert p.tieout_ok and not p.rejects and len(p.lines) == 10
    sections = {ln.description: ln.section for ln in p.lines}
    assert sections["TARIFA POR TRANSF.INTERBANCARIA B.L"] == "fee"  # "# " (IVA mark) removed
    assert sections["PAGO TARJETA CREDITO PAGO DIRECTO B"] == "payment"
    assert sections["CAPITALIZACION DE INTERESES EN CUEN"] == "interest_earned"
    assert sections["PAGO IESS BANCA EN LINEA"] == "movement"
    card = next(ln for ln in p.lines if ln.section == "payment")
    assert (card.amount, card.txn_date) == (Decimal("-1080.00"), date(2026, 7, 20))
    assert p.lines[2].amount == Decimal("600.00")


def test_a_misprinted_running_balance_fails() -> None:
    p = produbanco.parse(read_pages(produbanco_full(balance_delta="5")))
    failed = [c for c in p.checks if not c.ok]
    assert [c.name for c in failed] == ["Gaps in the running balance, line by line"]
    assert failed[0].actual == Decimal(10)  # 5 off at the misprint, 5 back on the next line


def test_year_end_statement_dates() -> None:
    lines = [
        ("Dic 20", "1", "DEBITO VISA", "-10.00"),
        ("Ene 3", "2", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "+20.00"),
    ]
    p = produbanco.parse(
        read_pages(produbanco_full(period="Del 15 Dic 2025 Al 14 Ene 2026", lines=lines))
    )
    assert p.tieout_ok
    assert [ln.txn_date for ln in p.lines] == [date(2025, 12, 20), date(2026, 1, 3)]


def test_wrong_layout_and_bad_lines() -> None:
    with pytest.raises(ParseError, match="Period"):
        produbanco.parse(["nothing"])
    with pytest.raises(ParseError, match="balance"):
        produbanco.parse(["Fecha Corte: Del 01 Jul 2026 Al 31 Jul 2026"])
    head = (
        "Fecha Corte: Del 01 Jul 2026 Al 31 Jul 2026\n"
        "Saldo inicial contable: 10.00\nSaldo final contable: 9.00\n"
    )
    p = produbanco.parse([head + "Quito Feb 30 1 DEBITO VISA -1.00 9.00 9.00\n?? -1.00 9.00 9.00"])
    assert len(p.rejects) == 2 and not p.tieout_ok


# The bank's order, with a balance that repeats on Jul 30 (-2,000 then +2,000, like Lauren's July).
ROUND_TRIP = [
    ("Jul 13", "1", "TARIFA POR TRANSF.INTERBANCARIA B.L", "-0.41"),
    ("Jul 15", "2", "TRANSFERENCIA INTERBANCARIA B.L.", "-241.00"),
    ("Jul 30", "3", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "-2,000.00"),
    ("Jul 30", "4", "TRANSFERENCIA INTERBANCARIA B.L.", "+2,000.00"),
    ("Jul 31", "5", "TRANSFERENCIA CTAS TERCEROS BCA ENL", "+2,000.00"),
    ("Jul 31", "6", "CAPITALIZACION DE INTERESES EN CUEN", "+0.01"),
]


def _scramble(pages: list[str], move: list[str]) -> list[str]:
    """The PDF's text with some lines moved up, as the July 2026 statement gave it: Jul 13, then
    the Jul 31 lines, then the rest."""
    lines = pages[0].splitlines()
    moved = [ln for ln in lines if any(f" {ref} " in ln and ln.startswith("Quito") for ref in move)]
    rest = [ln for ln in lines if ln not in moved]
    at = next(i for i, ln in enumerate(rest) if " 1 TARIFA" in ln) + 1
    return ["\n".join(rest[:at] + moved + rest[at:])]


def test_text_out_of_order_is_put_back_in_the_banks_order() -> None:
    pages = _scramble(read_pages(produbanco_full(lines=ROUND_TRIP, opening="5590.48")), ["5", "6"])
    assert " 5 TRANSFERENCIA" in pages[0].splitlines()[12]  # really out of order
    p = produbanco.parse(pages)
    assert p.tieout_ok and not p.rejects, [(c.name, c.actual) for c in p.checks if not c.ok]
    assert [ln.description[:14] for ln in p.lines][2:5] == [
        "TRANSFERENCIA ",
        "TRANSFERENCIA ",
        "TRANSFERENCIA ",
    ]
    assert [ln.amount for ln in p.lines] == [
        Decimal("-0.41"),
        Decimal("-241.00"),
        Decimal("-2000.00"),  # the repeated balance: the earlier date first, then +2,000
        Decimal("2000.00"),
        Decimal("2000.00"),
        Decimal("0.01"),
    ]


def test_a_missing_line_still_fails_whatever_the_order() -> None:
    pages = read_pages(produbanco_full(lines=ROUND_TRIP, opening="5590.48"))
    without = ["\n".join(ln for ln in pages[0].splitlines() if " 2 TRANSFERENCIA" not in ln)]
    p = produbanco.parse(without)
    failed = {c.name for c in p.checks if not c.ok}
    assert failed == {
        "Opening balance + lines = closing balance",
        "Gaps in the running balance, line by line",
    }


def test_english_period_months() -> None:
    from app.ingestion.detect import detect, read_pdf

    data = produbanco_full(
        period="Del 01 Aug 2026 Al 31 Aug 2026", lines=[("Ago 3", "1", "X", "+1.00")]
    )
    d = detect(read_pdf(data).text)
    assert (d.source, d.period_start, d.period_end) == (
        "produbanco",
        date(2026, 8, 1),
        date(2026, 8, 31),
    )
    assert produbanco.parse(read_pages(data)).tieout_ok
