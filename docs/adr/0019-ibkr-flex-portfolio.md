# ADR-019: The IBKR portfolio from the Flex Web Service, stored as daily positions and values

- Status: accepted
- Date: 2026-10-29

## Context

F22 (issue #58): the balance sheet should include the Interactive Brokers portfolio. It is done
when the value shown matches IBKR's for the same day. IBKR's Client Portal API needs a running
gateway and frequent re-authentication. The **Flex Web Service** is read-only and needs only a
token (valid up to a year) and a saved Flex Query. It returns end-of-day data, which is what a
household balance sheet needs.

## Decision

- **Flex Web Service.** The app sends `SendRequest?t=&q=&v=3`, then
  `GetStatement?t=&q=<reference>&v=3`. While IBKR answers "generation in progress" (1019 and
  similar codes), it retries every 5 seconds, up to a minute. IBKR's own errors (expired or
  invalid token, IP restriction) are shown as they are.
- **What is read:**
  - the latest *Net Asset Value in Base* row (total and cash);
  - *Open Positions* at summary level, converted to USD with the report's own rate;
  - *Cash Report* when the report has no net asset value section.

  The account number isn't stored.
- **What is stored:**
  - `core.investment_position` (migration 0021) holds each day's positions;
  - a `balance_snapshot` (source `ibkr`) holds the day's total, on the "Interactive Brokers"
    investment holding, which is created on the first read.

  So the balance sheet, net-worth series, projections and Claude see it like any other value.
  Reading the same day again replaces it.
- **When it is read:**
  - when Debt & Net Worth is opened and the last read is over 20 hours old;
  - on **Refresh from IBKR**.

  There's no scheduled job: the data is end-of-day, and reading it on opening keeps it current
  without another job or identity.
- **Without a token:** a Flex XML downloaded from Client Portal can be uploaded, and is read the
  same way.
- **Secrets:** `setup-ibkr.sh` asks for the token and Query ID without echoing them and stores them
  as Container App secrets. `main.bicep` and `bootstrap.sh` carry them on re-runs.
- **Claude:** `mart_reader` gets SELECT on `core.investment_position`, and `balance_sheet` lists
  positions under the investment item.

## Consequences

- The token expires at most a year after it's issued, and must be renewed in Client Portal and
  set again with `setup-ibkr.sh`.
- Values are end-of-day as of the last business day, not live prices.
- If the workbook's "Stock Market" item is the same account, it should be paused to avoid counting
  it twice.
