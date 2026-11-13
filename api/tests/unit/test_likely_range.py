"""ADR-096: the likely range of the forecast, from how much spending really varied."""

from datetime import date
from decimal import Decimal

from app.services import likely_range as lr


def _months(amounts: list[str]) -> dict[date, Decimal]:
    return {date(2026, k + 1, 1): Decimal(a) for k, a in enumerate(amounts)}


def test_surprises_are_what_each_month_spent_over_its_level() -> None:
    # Five months at 100 and one at 160: the level is 110.
    past = lr.surprises(_months(["100"] * 5 + ["160"]), {})
    assert past == [Decimal(-10)] * 5 + [Decimal(50)] and sum(past) == 0
    assert lr.surprises(_months(["100"] * 5), {}) == []  # too short to say
    # A month the season explains isn't a surprise: June spends 60 over a usual month.
    season = {date(2026, 6, 1): Decimal(60)}
    assert lr.surprises(_months(["100"] * 5 + ["160"]), season) == [Decimal(0)] * 6


def test_replays_are_repeatable_and_build_up_month_by_month() -> None:
    past = [Decimal(-10)] * 5 + [Decimal(50)]
    shares = [Decimal("0.5"), Decimal(1), Decimal(1)]
    runs = lr.replay(past, shares)
    assert len(runs) == lr.RUNS and runs == lr.replay(past, shares)
    # Half of the first month is left, so half of its surprise counts.
    assert {r[0] for r in runs} == {Decimal(-5), Decimal(25)}
    assert all(r[1] - r[0] in past for r in runs)
    low, high = lr.band(runs)[-1]
    assert low == Decimal(-25) and high > 0  # the good case: no surprise month at all
    assert lr.band(lr.replay([Decimal(10)], shares)) == [(5, 5), (15, 15), (25, 25)]
    assert lr.band([]) == []


def test_percentile_and_between() -> None:
    values = [Decimal(n) for n in range(10, 0, -1)]
    assert lr.percentile(values, lr.LOW) == 2 and lr.percentile(values, lr.HIGH) == 10
    assert lr.between(Decimal(5), Decimal(15), Decimal("0.5")) == 10


def test_chance_of_going_under_the_floor() -> None:
    # Two replays: 15 more spent by the end of the second month, or 15 less. The lowest day of
    # the second month is expected at 12.00, halfway through it.
    runs = [[Decimal(5), Decimal(15)], [Decimal(-5), Decimal(-15)]]
    lows = [(Decimal(100), Decimal(1)), (Decimal(12), Decimal("0.5"))]
    assert lr.chance_under(runs, lows, Decimal(0)) == 0  # 12 - 10 is still over zero
    assert lr.chance_under(runs, lows, Decimal(3)) == Decimal("0.50")
    assert lr.chance_under(runs, lows, Decimal(200)) == 1
    assert lr.chance_under([], lows, Decimal(0)) is None
