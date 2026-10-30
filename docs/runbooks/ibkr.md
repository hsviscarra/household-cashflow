# Interactive Brokers portfolio

Your IBKR positions, cash and account value appear on **Debt & Net Worth → Investments**. The
total counts in net worth as the "Interactive Brokers" item (F22, ADR-019).

## Update it (the usual way)

You need two connections in the Claude desktop app:
- the **Interactive Brokers (IBKR)** connector, signed in;
- the **household-cashflow** MCP connection (docs/runbooks/claude-mcp.md).

Then ask Claude:

> Update my IBKR portfolio in the cash flow app.

Claude reads your positions and account value from IBKR and calls `save_portfolio`. The result
shows the day, the total, the number of positions, and the change since the last save.

- **Same day twice:** the second save replaces the first.
- **"Don't tie out":** positions plus cash were more than 2% away from the net liquidation value,
  so nothing was saved. Usually a position was left out. Ask Claude to include every position and
  try again.
- **IBKR asks to sign in again:** reconnect the connector in Claude's settings (Connectors).
- **Reminder:** after a week without a save, the page suggests asking Claude.

## Every weekday, by itself

A Claude scheduled task, "Save IBKR portfolio to cash flow app", runs Monday to Friday at 4:52 pm
Quito time, after the market closes, and does the same as asking Claude.
- **Needs the Mac on:** it saves through the household-cashflow connection on the Mac, so the Mac
  must be on with Claude desktop open. A day it's off is skipped; the next run brings the value
  up to date.
- **Failures:** a push notification only when a save fails (Mac asleep, IBKR needs signing in
  again).
- **Pause or change it:** in Claude's scheduled tasks.

## Without Claude: upload a Flex report

In Client Portal, run an Activity Flex Query with these sections:
- Net Asset Value in Base;
- Open Positions, at Summary level;
- Cash Report.

Choose XML and download the file. On the Investments section, choose **Upload Flex report
(XML)**.

## Avoid counting it twice

If the workbook's "Stock Market" item is this same account, pause that item on Debt & Net Worth.
