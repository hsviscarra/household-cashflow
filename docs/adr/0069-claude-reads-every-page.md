# ADR-069: Claude reads taxes, groceries, bills and budget

Status: accepted (0.79.0, Nov 2026)

## Context

Hernan asks Claude about the household from a Claude Project through the read-only MCP server
(ADR-017). It covered the cash flow, lines, merchants, net worth, loans, reports, data status and
purchases, but not the Taxes, Groceries, Bills and Budget pages.

## Decision

Six more tools, each returning what its page's service already computes, as plain JSON (money
and dates as text): `taxes(year)`, `iva_return(month, person)`, `groceries_trends(month,
months)`, `groceries_products(month, months)`, `bills(month)` and `budget(month)`. Long lists are
cut (30 purchases, 40 products, no month-by-type cells) with the full count given. They read
only, through the same session as the other tools.

## Consequences

Claude can answer tax, grocery, bill and budget questions without the app open. A tool on Hernan's
Mac picks up new tools when its MCP server restarts.

## Amended (0.85.1, Nov 2026): the read-only login reads all of core

The six tools, and the bank-sync coverage that ADR-072 and ADR-073 added to data status and the
balance sheet, read tables the read-only login was never granted (budget plans, goals, tax
profiles, settings, `audit.load_log`), so they failed with "SELECT permission was denied" where
the login is used: the app's `/mcp` endpoint and the server on Hernan's Mac. The integration test
only called the older tools, on a database with no synced account. Migration 0050 grants
`mart_reader` SELECT on the whole `core` schema and on `audit.load_log`, so a new core table is
readable without another migration; raw statement lines, staging, the workbook's cells and the
change log stay out, and it still can't write. The test now calls every tool through the login.
