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
