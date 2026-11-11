# ADR-071: An account's opening date

Status: accepted (0.80.1, Nov 2026)

Lauren's Diners card is a few months old, yet Data Status asked for its August and September
statements: it expects every account from the first month it checks, and only `closed_on`
(ADR-026) could stop that. Migration 0047 adds `core.account.opened_on` (nullable date), set in
Settings → Accounts next to "Closed or suspended on". Data Status expects no statement before it:
the per-month check starts at the later of the month and the opening day, and the statement
timeline's gaps start there too. Earlier statements, if any, still load.
