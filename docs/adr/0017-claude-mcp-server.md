# ADR-017: A read-only MCP endpoint in the app, for the Claude desktop app

- Status: accepted
- Date: 2026-10-28

## Context

F18 (issue #20) asks for a read-only MCP server over the mart views, using a read-only SQL login
and connected to the Claude Project. It is done when Claude answers a month-over-month question
from live data. claude.ai's web and mobile connectors need OAuth sign-in. The Claude desktop app
can also run a local bridge (`mcp-remote`) that sends a fixed header.

## Decision

- **Desktop first** (Hernan's choice). Web and phone would need an OAuth authorization server
  in front of the endpoint, which can come later.
- **Inside the existing app.** The endpoint is `/mcp` on the same Container App, so there is no
  new service, no cost, and no new firewall rule. It uses the official Python `mcp` SDK
  (`FastMCP`), streamable HTTP, stateless, JSON responses. Each app instance runs its own
  session manager in its lifespan.
- **A bearer token, not the sign-in.** `MCP_TOKEN` is a Container App secret, compared in
  constant time. The Microsoft sign-in excludes `/mcp`, and the household allow-list doesn't
  apply there. Without a token the endpoint is off (404).
- **A read-only login.**
  - Migration 0018 creates the `mart_reader` role with `SELECT` on the `mart` schema only. The
    views read core tables through ownership chaining, so the role can't read a table directly.
  - At start-up the app creates or updates `cashflow_reader` from `READER_PASSWORD`, and adds
    it to the role. On Azure SQL Database that's a contained user; on SQL Server, a login.
  - Every tool queries through that login.
- **Tools that answer questions:**
  - `months`
  - `cash_flow`
  - `compare_months`: the done-when question, with cash flow side by side and group changes
  - `spending_by_category`
  - `spending_lines` (filters, at most 500)
  - `top_merchants`: merchants with reference numbers removed, like the Spending page
  - `interest_and_fees`

  The server's instructions explain the views, USD, the workbook-versus-statements months,
  "Uncategorized", and that incomplete months aren't savings.
- **Setup:** `infra/azure/setup-mcp.sh` stores the secrets, updates the sign-in exclusion,
  checks the endpoint, and prints the desktop config. `main.bicep` and `bootstrap.sh` carry the
  two secrets and the exclusion, so a later bootstrap re-run keeps them.

## Consequences

- Only the desktop app can use it for now. The token sits in its config file, so it must be
  kept private and rotated if exposed (`ROTATE=1`).
- The balance sheet, loans and saved reports aren't views, so Claude can't see them through
  this endpoint yet.
- The first question after a quiet period wakes the app and the database, which takes up to a
  minute.

## Amendment (0.23.0): the balance sheet, loans and saved reports

Claude can also read `balance_sheet`, `loans` and `monthly_report`. These are computed in Python
from several tables (statement balances, holdings, purchases paid through their category, loan
tables), and rebuilding that logic as views would duplicate it. So migration 0020 gives
`mart_reader` SELECT, and only SELECT, on exactly the tables that code reads. The tools run the
app's own services through the read-only login.

Still closed to Claude: statement lines' raw text, merchant rules, the change log and the
workbook's cells. Writes stay impossible; the integration test checks deletes and updates are
refused.
