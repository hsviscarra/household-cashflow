"""The likely range of the forecast (ADR-096, plan item C1): a band around the expected cash,
built from how much spending really varied.

For each of the last months (up to 24), the surprise is what was spent, with what its season
explains taken out, minus the average of those months. The forecast is then replayed many
times; each replay draws, for every month ahead, one past month's surprise whole, so groups that
ran high in the same month stay together. The band is where the middle 80% of the replays end up
(10th to 90th percentile), and the chance of dropping under the floor is the share of replays
that do.

It covers spending only: income and bills are taken as planned. The replays use a fixed seed, so
the same data always gives the same band. Decimal throughout; nothing here reads the database.
"""

import random
from datetime import date
from decimal import Decimal

# Assumptions (ADR-096).
HISTORY_MONTHS = 24  # the months whose surprises are replayed
MIN_MONTHS = 6  # fewer surprises than this isn't a range worth showing
RUNS = 1000
SEED = 20261113
LOW, HIGH = Decimal("0.10"), Decimal("0.90")

ZERO = Decimal(0)


def surprises(by_month: dict[date, Decimal], seasonal: dict[date, Decimal]) -> list[Decimal]:
    """What each of the last months spent over (or under) the average, after taking out what
    its season explains (`seasonal`: month -> spent over a usual month). Empty when the history
    is too short."""
    months = sorted(by_month)[-HISTORY_MONTHS:]
    if len(months) < MIN_MONTHS:
        return []
    plain = [by_month[m] - seasonal.get(m, ZERO) for m in months]
    average = sum(plain, ZERO) / len(plain)
    return [p - average for p in plain]


def replay(past: list[Decimal], shares: list[Decimal]) -> list[list[Decimal]]:
    """`RUNS` replays. Each is the extra spending built up by the end of every month ahead;
    `shares` is how much of each month is still to come (the rest of this month, then 1s)."""
    rng = random.Random(SEED)  # fixed seed: the same data, the same band
    out = []
    for _ in range(RUNS):
        extra, path = ZERO, []
        for share in shares:
            extra += rng.choice(past) * share
            path.append(extra)
        out.append(path)
    return out


def percentile(values: list[Decimal], p: Decimal) -> Decimal:
    """The value a share `p` of `values` is at or under (nearest rank)."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def band(runs: list[list[Decimal]]) -> list[tuple[Decimal, Decimal]]:
    """For each month ahead: the extra spending at its end in a good case (10th percentile,
    usually negative) and in a bad one (90th)."""
    months = len(runs[0]) if runs else 0
    return [
        (percentile([r[j] for r in runs], LOW), percentile([r[j] for r in runs], HIGH))
        for j in range(months)
    ]


def between(before: Decimal, after: Decimal, share: Decimal) -> Decimal:
    """The extra spending part of the way through a month: a straight line between its ends."""
    return before + (after - before) * share


def chance_under(
    runs: list[list[Decimal]], lows: list[tuple[Decimal, Decimal]], floor: Decimal
) -> Decimal | None:
    """The share of replays in which cash goes under the floor. `lows` is, for each month ahead,
    the expected lowest cash in it and how far through the month that day is (0 to 1)."""
    if not runs:
        return None
    under = 0
    for path in runs:
        before = ZERO
        for (lowest, share), after in zip(lows, path, strict=True):
            if lowest - between(before, after, share) < floor:
                under += 1
                break
            before = after
    return (Decimal(under) / len(runs)).quantize(Decimal("0.01"))
