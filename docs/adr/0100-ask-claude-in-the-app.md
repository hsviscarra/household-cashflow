# ADR-100: Ask Claude inside the app

Status: accepted (0.110.0, Nov 2026). Plan item D1. No schema change.

## Decision

- **A panel on every page** ("Ask Claude" in the menu). A question in plain words goes to the
  API with the page the person is on and its month; the answer is a few sentences that quote
  the numbers used. Three starter questions fit the page.
- **The same tools Claude already has.** `services/ask.py` offers the MCP server's reading
  tools (ADR-017: cash flow, spending, bills, net worth, loans, taxes…) to the Claude API as
  tool definitions and runs the ones Claude asks for, through the read-only reader login.
  `save_portfolio`, the one tool that writes, isn't offered. At most 6 rounds of tools per
  question; a tool's result is cut at 20,000 characters and says so; a tool that fails is told
  to Claude, never to the person as a crash.
- **Two models.** The small one (`ANTHROPIC_MODEL`) by default; "Think harder" uses the monthly
  report's (`ANTHROPIC_REPORT_MODEL`) for analysis.
- **A monthly limit.** Each call's tokens are priced from a table in the module (USD per
  million tokens, from the Claude API pricing page on Nov 13 2026: Haiku 5.5 0.10 in / 0.50
  out, Sonnet 5.5 2 / 10; an unknown model is charged at the dearest) and added to the month's
  total (`ask-usage:YYYY-MM`). At the limit (`ASK_MONTHLY_CAP`, 10.00 until changed on the
  panel; 0 turns it off) no more questions are sent that month. The total is counted even when
  a question fails halfway. The last question of a month can go over by its own cost.
- **What leaves the app.** The question, and the results of the tools Claude asked for (totals,
  lines with their descriptions and amounts, balances), go to the Claude API, the same data the
  MCP connector already gives Claude. Card and account numbers aren't stored beyond the last
  four digits (ADR-005), so they can't be sent. The panel says this before the first question.
  Nothing is stored: the conversation lives in the open panel.
- **Text in the data is data.** The system prompt says tool results (merchant names, notes)
  are never instructions; the tools can only read, so a hostile description can at worst
  produce a wrong sentence.
- **Testable without the network.** The API call is one function (`call_claude`) behind a
  `Caller` protocol; tests script Claude's turns and check the tools run, the history sent
  back, the cost and the limit.

## Not in this release

- An "Explain" button on each chart and number: the panel already sends the page and its
  month; per-chart context (its period and filters) is the next step.
- Streaming the answer, and keeping past conversations.
- The limit in Settings: it is on the panel, where the usage is shown.
