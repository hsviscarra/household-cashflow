"""Seasons (ADR-096, plan item C2): how each spending group moves through the year.

A group's index for a calendar month says how that month compares with the group's usual month:
1 is a usual month, 2 is twice as much (December), 12 is a whole year in one month (school
enrollment, a yearly insurance). It is the median, over the complete calendar years in the
history, of the month's spending divided by that year's monthly average, so something that
happened once doesn't become a season and something that happens every year does. A year's
indices add up to 12: seasons move spending between months, they don't add any.

A seasonal group is then forecast by its own year: its usual month (its last twelve months,
divided by twelve) times the month's index. With less than two complete years of history no
group has an index and the forecast is the plain average it was before.

Pure functions over amounts by group and month; nothing here reads the database.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

# Assumptions (ADR-096).
MIN_YEARS = 2  # complete calendar years a group needs before its pattern is followed
MIN_MONTHLY = Decimal(20)  # a group smaller than this a month has no pattern worth following
NOTE_MIN = Decimal(50)  # a seasonal difference smaller than this isn't worth a note
MONTHS_IN_YEAR = 12

ZERO = Decimal(0)
ONE = Decimal(1)
FLAT = [ONE] * MONTHS_IN_YEAR

# (group, first day of the month) -> spending, positive.
History = dict[tuple[int, date], Decimal]
Index = list[Decimal]  # January to December


def complete_years(first: date, last: date) -> list[int]:
    """Calendar years wholly inside the history, which runs from `first` to `last` (months)."""
    start = first.year if first.month == 1 else first.year + 1
    end = last.year if last.month == MONTHS_IN_YEAR else last.year - 1
    return list(range(start, end + 1))


def index(by_month: dict[date, Decimal], years: list[int]) -> Index:
    """One series' index, January to December. Flat (all 1) without enough years, or when the
    series has no month that repeats."""
    ratios: list[list[Decimal]] = [[] for _ in range(MONTHS_IN_YEAR)]
    used = 0
    for y in years:
        months = [by_month.get(date(y, k, 1), ZERO) for k in range(1, MONTHS_IN_YEAR + 1)]
        usual = sum(months, ZERO) / MONTHS_IN_YEAR
        if usual < MIN_MONTHLY:
            continue
        used += 1
        for k, amount in enumerate(months):
            ratios[k].append(amount / usual)
    if used < MIN_YEARS:
        return list(FLAT)
    medians = [Decimal(str(median(r))) for r in ratios]
    level = sum(medians, ZERO) / MONTHS_IN_YEAR
    if level <= 0:
        return list(FLAT)
    return [m / level for m in medians]


def by_group(history: History) -> dict[int, dict[date, Decimal]]:
    out: dict[int, dict[date, Decimal]] = defaultdict(dict)
    for (group, month), amount in history.items():
        out[group][month] = amount
    return out


def total(history: History) -> dict[date, Decimal]:
    """Every group together, by month."""
    out: dict[date, Decimal] = defaultdict(Decimal)
    for (_, month), amount in history.items():
        out[month] += amount
    return dict(out)


def indices(history: History) -> dict[int, Index]:
    """Each group's index. Groups without a pattern aren't in it: read them as flat."""
    if not history:
        return {}
    months = [m for _, m in history]
    years = complete_years(min(months), max(months))
    out = {}
    for group, series in by_group(history).items():
        found = index(series, years)
        if found != FLAT:
            out[group] = found
    return out


def of(idx: Index | None, month: date) -> Decimal:
    return ONE if idx is None else idx[month.month - 1]


def usual(history: History, months: list[date], idx: dict[int, Index]) -> dict[int, Decimal]:
    """The usual month of each group that has a season: what it spent in `months` (a whole
    year, so every season is in it once) divided by how many they are."""
    if not months:
        return {}
    spent: dict[int, Decimal] = defaultdict(Decimal)
    for (group, month), amount in history.items():
        if group in idx and month in months:
            spent[group] += amount
    return {group: amount / len(months) for group, amount in spent.items()}


def over_usual(level: dict[int, Decimal], idx: dict[int, Index], month: date) -> dict[int, Decimal]:
    """What each seasonal group spends in a month over its usual month (negative: under)."""
    return {group: amount * (of(idx.get(group), month) - ONE) for group, amount in level.items()}


def notes(
    level: dict[int, Decimal], idx: dict[int, Index], month: date
) -> list[tuple[int, Decimal]]:
    """The groups that make a month heavier than a usual one, biggest first: (group, how much
    more than usual). Months that run light aren't worth a note."""
    out = [(g, more) for g, more in over_usual(level, idx, month).items() if more >= NOTE_MIN]
    return sorted(out, key=lambda x: -x[1])
