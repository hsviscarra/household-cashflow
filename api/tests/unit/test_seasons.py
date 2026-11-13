"""ADR-096: a group's index through the year, and everyday spending forecast from it."""

from datetime import date
from decimal import Decimal

from app.services import seasons

CENT = Decimal("0.01")
SCHOOL, FOOD = 1, 2


def _year(year: int, usual: str, **other: str) -> dict[date, Decimal]:
    """A year at `usual` a month, except the months named (m8="300")."""
    out = {date(year, k, 1): Decimal(usual) for k in range(1, 13)}
    for key, amount in other.items():
        out[date(year, int(key[1:]), 1)] = Decimal(amount)
    return out


def test_complete_years() -> None:
    assert seasons.complete_years(date(2023, 1, 1), date(2025, 12, 1)) == [2023, 2024, 2025]
    # A year that starts in March or ends in October isn't whole.
    assert seasons.complete_years(date(2023, 3, 1), date(2026, 10, 1)) == [2024, 2025]
    assert seasons.complete_years(date(2026, 2, 1), date(2026, 10, 1)) == []


def test_a_month_that_repeats_every_year_is_a_season() -> None:
    # 100 a month and 300 every August: a year is 1,400, so a usual month is 116.67.
    series = {**_year(2024, "100", m8="300"), **_year(2025, "100", m8="300")}
    idx = seasons.index(series, [2024, 2025])
    assert idx[7].quantize(Decimal("0.0001")) == Decimal("2.5714")  # 300 / 116.67
    assert idx[0].quantize(Decimal("0.0001")) == Decimal("0.8571")  # 100 / 116.67
    assert sum(idx).quantize(CENT) == Decimal("12.00")


def test_once_is_not_a_season_and_short_or_small_histories_are_flat() -> None:
    # Two plain years and one with a big August: the median August is a usual month.
    series = {**_year(2023, "100"), **_year(2024, "100", m8="900"), **_year(2025, "100")}
    assert seasons.index(series, [2023, 2024, 2025]) == seasons.FLAT
    assert seasons.index(_year(2025, "100", m8="300"), [2025]) == seasons.FLAT  # one year
    small = {**_year(2024, "5", m8="60"), **_year(2025, "5", m8="60")}  # under 20 a month
    assert seasons.index(small, [2024, 2025]) == seasons.FLAT
    # A whole year in one month: the index is 12 there and 0 elsewhere.
    yearly = {date(y, 8, 1): Decimal(600) for y in (2024, 2025)}
    idx = seasons.index(yearly, [2024, 2025])
    assert idx[7] == 12 and sum(idx) == 12


def test_everyday_spending_follows_each_groups_season() -> None:
    history: seasons.History = {}
    for year in (2024, 2025):
        history |= {(SCHOOL, m): a for m, a in _year(year, "100", m8="300").items()}
        history |= {(FOOD, m): a for m, a in _year(year, "500").items()}
    idx = seasons.indices(history)
    assert set(idx) == {SCHOOL}  # food has no pattern: it isn't in it and reads as flat

    # School's usual month is its last twelve months over twelve: 1,400 / 12.
    year = [date(2025, k, 1) for k in range(1, 13)]
    level = seasons.usual(history, year, idx)
    assert set(level) == {SCHOOL} and level[SCHOOL].quantize(CENT) == Decimal("116.67")
    # August spends 183.33 over a usual month; every other month 16.67 under. A year adds to 0.
    assert seasons.over_usual(level, idx, date(2027, 8, 1))[SCHOOL].quantize(CENT) == Decimal(
        "183.33"
    )
    assert seasons.over_usual(level, idx, date(2026, 12, 1))[SCHOOL].quantize(CENT) == Decimal(
        "-16.67"
    )
    assert sum(seasons.over_usual(level, idx, m)[SCHOOL] for m in year).quantize(CENT) == 0
    assert seasons.notes(level, idx, date(2026, 12, 1)) == []  # a light month: no note
    [(group, more)] = seasons.notes(level, idx, date(2027, 8, 1))
    assert group == SCHOOL and more.quantize(CENT) == Decimal("183.33")
    assert seasons.usual(history, [], idx) == {} and seasons.indices({}) == {}
    assert seasons.total(history)[date(2025, 8, 1)] == 800
