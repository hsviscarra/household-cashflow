"""ADR-098: net worth five to ten years ahead."""

from datetime import date
from decimal import Decimal

from app.services import long_view as lv

D = Decimal
TODAY = date(2026, 12, 15)  # no whole month left this year: year 0 is today


def _start(**kwargs: object) -> lv.Start:
    base: dict[str, object] = {
        "cash": D(1000),
        "investments": D(10000),
        "property": D(0),
        "vehicles": D(0),
        "other_assets": D(0),
        "other_debts": D(0),
        "kept_a_year": D(0),
    }
    return lv.Start(**{**base, **kwargs})  # type: ignore[arg-type]


def test_investments_compound_at_the_three_returns() -> None:
    a = lv.Assumptions(years=2, returns=(D("0.00"), D("0.05"), D("0.10")))
    y0, y1, y2 = lv.project(_start(), a, TODAY)
    assert (y0.year, y0.end) == (2026, date(2026, 12, 31))
    assert y0.investments == {"low": D(10000), "expected": D(10000), "high": D(10000)}
    assert y1.investments["expected"] == D("10500.00")
    # 10,000 x 1.05^2 and x 1.10^2.
    assert (y2.investments["expected"], y2.investments["high"]) == (D("11025.00"), D("12100.00"))
    assert y2.net("low") == D(11000) and y2.net("high") == D(13100)


def test_what_is_kept_pays_the_loans_first_then_stays_or_is_invested() -> None:
    # A loan with a table: 6,000 owed, 3,000 paid off a year, 300 then 100 of interest.
    loan = lv.LoanPath(
        "Car",
        D(6000),
        balances=(D(6000), D(3000), D(0)),
        interest=(D(0), D(300), D(100)),
        paid_off=date(2028, 12, 1),
    )
    s = _start(investments=D(0), kept_a_year=D(5000), loans=(loan,))
    a = lv.Assumptions(years=3, returns=(D(0), D(0), D(0)), invest_share=D("0.5"))
    y0, y1, y2, y3 = lv.project(s, a, TODAY)
    assert (y0.cash, y0.loans, y0.net("expected")) == (D(1000), D(6000), D(-5000))
    # Year 1: 5,000 kept, 300 goes in interest; 3,000 pays the loan down; of the 1,700 left,
    # half is invested.
    assert (y1.kept, y1.loans) == (D(4700), D(3000))
    assert (y1.cash, y1.investments["expected"]) == (D(1850), D(850))
    # Net worth grows by what was kept after interest, wherever it went.
    assert y1.net("expected") - y0.net("expected") == D(4700)
    assert y2.net("expected") - y1.net("expected") == D(4900)
    # After the table ends the loan is gone and everything kept is free.
    assert (y3.loans, y3.kept) == (D(0), D(5000))
    assert y3.net("expected") == D(-5000) + 4700 + 4900 + 5000


def test_a_loan_without_a_table_goes_down_by_its_payments() -> None:
    loan = lv.LoanPath("Family", D(2500), yearly_payment=D(1200))
    assert lv.loan_balances(loan, 6, 4) == [
        (D(1900), D(0)),  # six months left this year
        (D(700), D(0)),
        (D(0), D(0)),
        (D(0), D(0)),
    ]


def test_property_vehicles_the_rest_of_this_year_and_milestones() -> None:
    s = _start(
        cash=D(0),
        investments=D(0),
        property=D(100000),
        vehicles=D(20000),
        other_assets=D(500),
        other_debts=D(1500),
        kept_a_year=D(12000),
    )
    a = lv.Assumptions(years=1, property_growth=D("0.02"), vehicle_growth=D("-0.10"))
    # From June 20 there are six whole months left: half a year of everything.
    y0, y1 = lv.project(s, a, date(2026, 6, 20))
    assert (y0.kept, y0.cash) == (D(6000), D(6000))
    assert (y0.property, y0.vehicles) == (D(101000), D(19000))
    assert y1.property == D("103020.00") and y1.vehicles == D("17100.00")
    assert y1.net("expected") == D(18000) + D("103020") + D(17100) + 500 - 1500

    years = [y0, y1]
    lv.place(
        years,
        [
            (date(2027, 9, 1), "School starts"),
            (date(2027, 3, 1), "Car paid off"),
            (date(2031, 1, 1), "Too far"),
        ],
    )
    assert y0.milestones == [] and y1.milestones == ["Car paid off", "School starts"]
