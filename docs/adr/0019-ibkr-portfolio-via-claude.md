# ADR-019: The IBKR portfolio, read by Claude's IBKR connector and saved through the MCP endpoint

- Status: accepted
- Date: 2026-10-29

## Context

F22 (issue #58): the balance sheet should include the Interactive Brokers portfolio. It is done
when the value shown matches IBKR's for the same day.

Hernan already uses IBKR's connector in Claude. It is signed in to his account and returns
positions (`get_account_positions`), the account value (`get_account_summary`) and cash
(`get_account_balances`). That sign-in belongs to Claude, so the app on Azure can't use it.

A first draft of this feature used IBKR's Flex Web Service, which needs a separate token and
saved query. Hernan chose the connector he already has.

## Decision

- **Claude reads, the app stores.** When Hernan asks "update my IBKR portfolio in the cash flow
  app", Claude reads the connector and calls `save_portfolio` on the app's MCP endpoint. Arguments:
  - `total`: net liquidation value;
  - `cash`;
  - every position: symbol, quantity, price, value, average price, unrealized gain, currency;
  - `as_of`: optional, defaults to today.
- **Tie-out.** Positions plus cash must be within 2% of the total, or nothing is saved. IBKR's
  net liquidation value also includes accrued dividends and interest, a few dollars. A position
  left out or a misread number is refused, not saved.
- **What is stored:**
  - `core.investment_position` (migration 0021) holds each day's positions;
  - a `balance_snapshot` (source `ibkr`) holds the day's total, on the "Interactive Brokers"
    investment holding, which is created on the first save;
  - one `audit.load_log` row records who saved it, how many positions, and the total.

  Saving the same day again replaces that day. The account number isn't stored.
- **One write on the MCP endpoint.** `save_portfolio` writes with the app's own login and touches
  only the tables above. Every other tool still reads through `cashflow_reader`. ADR-017 is
  amended.
- **The page** shows total, cash, unrealized gain and the positions. After a week without a save,
  it suggests asking Claude.
- **Fallback.** A Flex report (XML) downloaded from Client Portal can still be uploaded on the
  page, and is read the same way. No token or secret is needed for that.
- **Claude reads it back.** `mart_reader` gets SELECT on `core.investment_position`, and
  `balance_sheet` lists the positions under the investment item.

## Consequences

- Values update when Hernan asks Claude, not by themselves. The page's reminder after a week
  covers the gap.
- No IBKR secret lives in Azure; when IBKR asks to re-authenticate, that happens in Claude's
  connector settings.
- Prices are whatever the connector returns at that moment: live during market hours.
- If the workbook's "Stock Market" item is the same account, pause it so the account isn't counted
  twice.
