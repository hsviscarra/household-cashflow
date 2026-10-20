"""Golden test on a synthetic Capital One statement with the real layout."""

from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.detect import read_pages
from app.ingestion.parsers import capitalone
from app.ingestion.parsers.base import ParseError
from tests.fixtures.statements import capitalone_full


def test_golden_statement_ties_out() -> None:
    p = capitalone.parse(read_pages(capitalone_full()))
    assert (p.period_start, p.period_end) == (date(2026, 9, 4), date(2026, 10, 3))
    assert (p.opening_balance, p.closing_balance) == (Decimal("1000.00"), Decimal("806.75"))
    assert p.tieout_ok and not p.rejects
    assert [c.name for c in p.checks][:2] == ["Card #4003 transactions", "Card #4162 transactions"]

    by_section = {
        s: [ln for ln in p.lines if ln.section == s] for s in ("payment", "purchase", "interest")
    }
    assert len(by_section["purchase"]) == 9
    pay = by_section["payment"][0]
    assert (pay.amount, pay.person, pay.cardholder) == (Decimal("500.00"), "Lauren", "4003")
    interest = by_section["interest"][0]
    assert (interest.amount, interest.txn_date) == (Decimal("-10.00"), date(2026, 10, 3))

    first = by_section["purchase"][0]
    assert (first.txn_date, first.post_date, first.amount) == (
        date(2026, 9, 2),
        date(2026, 9, 4),
        Decimal("-12.50"),
    )
    refund = next(ln for ln in p.lines if "REFUND" in ln.description)
    assert refund.amount == Decimal("30.00") and refund.person == "Hernan"


def test_tieout_fails_when_the_printed_total_differs() -> None:
    p = capitalone.parse(read_pages(capitalone_full(printed_total_delta="1.00")))
    failed = [c.name for c in p.checks if not c.ok]
    assert "Transactions, all cards" in failed
    assert not p.tieout_ok


def test_lines_outside_a_section_are_rejected() -> None:
    p = capitalone.parse(
        read_pages(
            capitalone_full(
                extra_lines=["Interest Charge Calculation", "Sep 9 Sep 9 ODD LINE $1.00"]
            )
        )
    )
    assert [r.text for r in p.rejects] == ["Sep 9 Sep 9 ODD LINE $1.00"]
    assert not p.tieout_ok


def test_cycle_across_new_year() -> None:
    p = capitalone.parse(
        read_pages(
            capitalone_full(
                period=("Dec 04, 2026", "Jan 03, 2027"),
                lauren=[
                    ("Dec 30", "Jan 2", "UBER EATS SAN JOSE", "10.00"),
                    ("Jan 2", "Jan 3", "UBER EATS SAN JOSE", "5.00"),
                ],
                hernan=[],
                payment_dates="Dec 27 Dec 28",
            )
        )
    )
    dates = [ln.txn_date for ln in p.lines if ln.section == "purchase"]
    assert dates == [date(2026, 12, 30), date(2027, 1, 2)]
    assert p.tieout_ok


def test_wrong_layout_raises() -> None:
    with pytest.raises(ParseError, match="Billing cycle"):
        capitalone.parse(["no period here"])
    with pytest.raises(ParseError, match="previous_balance"):
        capitalone.parse(["Sep 04, 2026 - Oct 03, 2026"])
    with pytest.raises(ValueError):
        capitalone._year_for("Mar 1", date(2026, 9, 4), date(2026, 10, 3))
