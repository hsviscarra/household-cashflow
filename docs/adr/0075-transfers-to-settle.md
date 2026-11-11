# ADR-075: Transfers to settle

Status: accepted (0.84.0, Nov 2026)

## Context

123 transfers had no other side, and the only tool was "Match again". Most go to or come from
places the app doesn't follow (Lauren's flexible savings, Wise, money exchangers, cash, people),
some pair with a line automatic matching skipped, and some aren't transfers at all.

## Decision

- People & transfers gets a tab, **Transfers to settle** (`/transfers`): every unmatched transfer,
  newest first, bunched by text and amount (`transfers.workbench`, `GET /api/transfers/workbench`).
  Each line lists up to 4 candidates: the opposite amount in another account, not paired yet,
  within 7 days (10 across countries).
- Three answers: **Pair with…** (`POST /api/transfers/pair`: both become a transfer in Card
  Payment or Between Own Accounts, chosen by a person); **The other side is…** a named place or a
  person (`POST /api/transfers/outside`: settled on its own as in ADR-058, with "Other side: …" in
  its note); or **It isn't a transfer** (a category, through the usual line edit). Ticks apply an
  answer to several lines of a bunch at once. Every change is logged.
- To do's transfers section links to the page.

## Consequences

Places are a fixed list plus the People; a new place is a code change until accounts like the
flexible savings are added to the app, after which pairing replaces "outside".
