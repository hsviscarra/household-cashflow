"""Golden test on a synthetic Bank of America combined statement with the real layout."""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.detect import read_pages
from app.ingestion.parsers import bofa
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import bofa_full


def test_both_accounts_tie_out() -> None:
    p = bofa.parse(read_pages(bofa_full()))
    assert (p.period_start, p.period_end) == (date(2026, 8, 22), date(2026, 9, 22))
    assert p.balances == {
        "8872": (Decimal("2000.00"), Decimal("4245.00")),
        "1862": (Decimal("100.00"), Decimal("120.00")),
    }
    assert p.tieout_ok and not p.rejects
    names = [c.name for c in p.checks]
    assert "•••• 8872 beginning balance + lines = ending balance" in names
    assert "•••• 1862 service fees (section total)" in names

    by_acct = {a: [ln for ln in p.lines if ln.account == a] for a in ("8872", "1862")}
    assert len(by_acct["8872"]) == 5 and len(by_acct["1862"]) == 2
    salary = by_acct["8872"][0]
    assert (salary.amount, salary.reference, salary.txn_date) == (
        Decimal("4000.00"),
        "August",
        date(2026, 9, 21),
    )
    fee = by_acct["1862"][1]
    assert (fee.section, fee.amount) == ("fee", Decimal("-5.00"))


def test_wrapped_descriptions_continue_across_lines_and_pages() -> None:
    p = bofa.parse(read_pages(bofa_full()))
    card = next(ln for ln in p.lines if ln.description.startswith("CAPITAL ONE"))
    assert card.description.endswith("ID:9999999 WEB")
    zelle = next(ln for ln in p.lines if ln.description.startswith("Zelle"))
    assert zelle.description.endswith("WEB")
    assert not any("Pause and verify" in ln.description for ln in p.lines)


def test_a_wrong_printed_total_fails_the_tie_out() -> None:
    p = bofa.parse(read_pages(bofa_full(printed_withdrawals_delta="-10.00")))
    assert [c.name for c in p.checks if not c.ok] == ["•••• 8872 withdrawals"]
    assert not p.tieout_ok


def test_wrong_layout_raises() -> None:
    with pytest.raises(ParseError, match="Statement period"):
        bofa.parse(["nothing"])
    with pytest.raises(ParseError, match="Account number"):
        bofa.parse(["Your combined statement for August 22, 2026 to September 22, 2026"])


def test_lines_outside_a_section_are_rejected() -> None:
    page = "\n".join(
        [
            "Account number: 0000 1111 8872",
            "Account summary",
            "Beginning balance on August 22, 2026 $10.00",
            "Ending balance on September 22, 2026 $10.00",
            "09/01/26 STRAY LINE -1.00",
            "Deposits and other additions",
            "13/45/26 BAD DATE 1.00",
        ]
    )
    p = bofa.parse(["for August 22, 2026 to September 22, 2026", page])
    assert [r.reason for r in p.rejects] == [
        "Line outside a known section",
        "time data '13/45/26' does not match format '%m/%d/%y'",
    ]
    assert not p.tieout_ok
