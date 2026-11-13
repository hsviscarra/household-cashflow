# ADR-096: The forecast as a range, with seasons and saved scenarios

Status: accepted (0.106.0, Nov 2026). Plan items C1, C2 and C3. No schema change. One release
(ADR-092). Builds on ADR-013 and ADR-033; the forecast's events (bills, income, loans,
installments, what-ifs, income tax) are untouched.

## Decision

### Seasons (C2) — `services/seasons.py`

- **A group's index** for a calendar month is the median, over the complete calendar years in
  the history, of that month's spending divided by the year's monthly average. Median, so what
  happened once isn't a season; a year's indices add up to 12, so seasons move spending
  between months and add none. A group needs two complete years and at least 20 a month.
- **What history.** Everyday spending only: lines in categories no recurring item pays. Bills
  are planned, not forecast, and this reads statement months and the old sheets on the same
  terms (the sheets can't tell a bill from a purchase; the category can).
- **The forecast.** A seasonal group is forecast by its own year in place of its share of the
  average: its usual month (its last twelve months over twelve) times the month's index. The
  average is first cleared of what those groups weighed in the months it was taken over, so a
  window that happens to hold August's enrollment doesn't raise every month ahead.
- **Cards.** What a seasonal group puts on credit cards doesn't leave the bank that month: only
  what the month spent over a usual month is added, and to the month after, because the usual
  part is already inside the card payments (recurring items). The card share is per group, from
  the last twelve months of statement lines.
- It can be turned off ("Follow the seasons"); then every month gets the average, as before.
  Without two complete years nothing changes at all.

### A likely range (C1) — `services/likely_range.py`

- **Surprises.** For each of the last 24 months of everyday spending: what was spent, less what
  its season explains, less the average of those months.
- **Replays.** The months ahead are replayed 1,000 times; each month draws one past month's
  surprise whole (so groups that ran high together stay together). The band is the 10th to
  90th percentile of cash, day by day; the chance of going under the floor is the share of
  replays that do. A fixed seed: the same data gives the same band. Decimal throughout.
- **What it doesn't cover.** Income and bills are taken as planned. A salary that varies or a
  bill that changes isn't in the band; the page says so. Fewer than 6 months: no band.

### Saved scenarios (C3) — `web/src/components/Scenarios.tsx`

- A set of what-ifs is saved under a name in the person's settings (`forecast:scenarios`, at
  most 12) and up to three are compared with the forecast as it is: lowest cash, first day
  short, cash at each month's end, the difference at the end, and the daily lines together.
- Each comparison is the existing scenario endpoint, once per scenario. No table: a scenario is
  a short list a person keeps, like a saved view (ADR-030).

## Assumptions (constants, in the two modules)

`MIN_YEARS` 2, `MIN_MONTHLY` 20, `NOTE_MIN` 50 (a seasonal note), `HISTORY_MONTHS` 24,
`MIN_MONTHS` 6, `RUNS` 1,000, band 10%–90%.

## Not in this release

- Income that varies (the band would need the same treatment for income).
- Scenarios shared between the two of you: they are per person, like saved views.
- C4 (five to ten years) builds on this and comes with phase 5.

## Check on real data

The numbers are tested against small histories with known answers. Whether the seasons found
in the household's own history are the ones Hernan recognises (school, December) is to be
looked at on the live page; "Follow the seasons" turns them off if they aren't.
