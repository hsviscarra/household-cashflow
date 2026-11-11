# ADR-073: Four measures, fair comparisons and the new Home

Status: accepted (0.82.0, Nov 2026)

## Context

"Kept −9,708" for 2026 read as a loss: the app counted savings, investing and the new house as
money out. Home compared November 1–11 with the whole of October ("−100% vs Oct"). Hernan asked
for a home page that shows everything at a glance (money per bank account, cash flow, net worth,
investments, budget, goals), month by month, with an explanation on every number. Proposal in the
doc "Cash flow app — redesign proposal"; he approved the measures and the blocks on Nov 11 2026.

## Decision

- `services/measures.py` and `GET /api/cashflow/measures`: Money in, Spent (purchases, bills,
  fees and interest less refunds; the workbook's card payments too), Set aside (savings,
  investing, the house, loan payments), Free cash (in − spent) and Left over (free cash − set
  aside; the old "Kept"). A running month counts its first N days and is compared with the same N
  days of the month before; a finished month with the whole month before. The last 12 months
  come with it.
- Home is rebuilt as widgets: Needs you, This month so far (the four measures), Your money now
  (each bank account's balance with its date and source, grey when older than 35 days, cards
  owed), Net worth (total, change this month and year, 24-month line, assets by class), Cash flow
  12 months (spent and set aside stacked, money in as a line), Investments (IBKR value, change,
  gain, top 5), Budget (planned vs actual with today's pace), Goals, Coming up (with the lowest
  cash ahead), Where it went and Inbox. A month picker changes the month; "Complete through" says
  how current the data is. Saved layouts from before start from the new default.
- Net worth uses bank sync's balance for synced accounts when it is newer than the last
  statement.
- `explain.ts` holds every explanation once; `<Info>` (an ⓘ) shows it on hover, focus or tap.
  KpiCard takes `info`. The yearly Cash flow uses the four measures in the spending view.

## Consequences

The cash view keeps Money in / Money out / Kept, since it counts bank money only.
