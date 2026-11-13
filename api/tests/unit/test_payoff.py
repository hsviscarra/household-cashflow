"""ADR-097: debt payoff order, compared."""

from decimal import Decimal

import pytest

from app.services import payoff
from app.services.payoff import Debt

CARD = Debt("card", "Card", Decimal(5000), Decimal("0.24"), Decimal(150))
CAR = Debt("car", "Car", Decimal(1000), Decimal("0.06"), Decimal(50))


def test_one_debt_against_the_loan_formula() -> None:
    # 1,000 at 12% a year (1% a month) paid 100 a month: n = -ln(1 - rB/P) / ln(1 + r) = 10.6,
    # so 11 payments; after 10 the balance is 1000 x 1.01^10 - 100 x (1.01^10 - 1) / 0.01 = 58.40,
    # which costs 0.58 more in the last month: 58.98 of interest in all.
    plan = payoff.simulate([Debt("a", "A", Decimal(1000), Decimal("0.12"), Decimal(100))])
    assert plan.months == 11 and plan.order == ["a"] and plan.paid_in == {"a": 11}
    assert abs(plan.interest - Decimal("58.98")) <= Decimal("0.02")  # cents rounded each month


def test_no_interest_and_nothing_owed() -> None:
    plan = payoff.simulate([Debt("a", "A", Decimal(300), Decimal(0), Decimal(100))])
    assert (plan.months, plan.interest) == (3, 0)
    assert payoff.simulate([]).months == 0
    assert payoff.simulate([Debt("a", "A", Decimal(0), Decimal("0.2"), Decimal(10))]).months == 0


def test_a_payment_under_the_interest_never_ends() -> None:
    # 2% a month on 1,000 is 20; paying 15 goes nowhere.
    plan = payoff.simulate([Debt("a", "A", Decimal(1000), Decimal("0.24"), Decimal(15))])
    assert plan.months is None and plan.interest > 0


def test_the_two_orders() -> None:
    assert [d.key for d in payoff.priority([CAR, CARD], "avalanche")] == ["card", "car"]
    assert [d.key for d in payoff.priority([CARD, CAR], "snowball")] == ["car", "card"]
    with pytest.raises(ValueError, match="Unknown strategy"):
        payoff.priority([CARD], "luck")

    c = payoff.compare([CARD, CAR], Decimal(200))
    # The same money every month either way, so the same order of magnitude of time; the
    # highest rate first costs less interest, the smallest balance first closes a debt sooner.
    assert c.avalanche.interest < c.snowball.interest < c.minimums.interest
    assert c.saved == c.snowball.interest - c.avalanche.interest and c.saved > 0
    assert c.snowball.order == ["car", "card"]
    assert c.snowball.paid_in["car"] < c.avalanche.paid_in["car"]
    assert c.avalanche.months is not None and c.minimums.months is not None
    assert c.avalanche.months < c.minimums.months
    # Minimums only, nothing rolled over: each debt on its own.
    alone = payoff.simulate([CARD])
    assert c.minimums.paid_in["card"] == alone.months


def test_freed_minimums_roll_over() -> None:
    # Two debts without interest, 100 a month each, no extra: the first is gone in 2 months and
    # its 100 then goes to the second: 2 x 100, then 200 a month for the 800 left.
    small = Debt("s", "Small", Decimal(200), Decimal(0), Decimal(100))
    big = Debt("b", "Big", Decimal(1000), Decimal(0), Decimal(100))
    plan = payoff.simulate([small, big], Decimal(0), "snowball")
    assert plan.paid_in == {"s": 2, "b": 6}
    assert payoff.simulate([small, big]).paid_in == {"s": 2, "b": 10}
