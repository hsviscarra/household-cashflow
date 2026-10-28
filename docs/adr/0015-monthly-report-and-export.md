# ADR-015: Monthly report from computed facts, findings by Claude or rules, exports of the views

- Status: accepted
- Date: 2026-10-28

## Context

F16 (issue #18) adds a monthly narrative (3 to 5 findings) and CSV and Excel export of any view.
It is done when the October 2026 report is generated. Every number the report needs is already
on a page: cash flow (F2, F8), spending (F13), subscriptions and interest (F14), the balance sheet
and loan tables (F14, ADR-014), projections and alerts (F15), and Data Status (F12).

## Decision

- **Facts first, computed by the app.** `services/report.facts()` gathers the month from the same
  services the pages use:
  - cash flow, against last month and the three months before;
  - the biggest group changes, top categories and merchants;
  - subscriptions, including those that started or stopped;
  - interest and fees, month and year to date;
  - net worth and loans;
  - spending alerts;
  - the projection's lowest cash, for the current or last month only;
  - whether the month is complete.

  Claude never does arithmetic. It only writes from those facts.
- **Like-for-like net worth.** The month's change counts only items valued at both month ends.
  Items first valued in the month (a house entered today, a card's first statement) are listed
  apart and are not a gain.
- **No misleading comparisons.** "Uncategorized" is lines waiting for a category, not a kind of
  spending, so it is left out of group changes and alerts. In an incomplete month, a drop against
  last month is mostly statements not loaded yet, so the rules don't report a "biggest change",
  and Claude is told the same.
- **Findings by Claude when it is on, by rules otherwise.**
  - Claude: `ANTHROPIC_REPORT_MODEL`, default Claude Sonnet 5.5, with a JSON-schema answer of
    3 to 5 findings (title, text, tone). The text must quote the facts' numbers.
  - Rules: without a key, or when Claude fails. In that case the page says so.
  - What Claude receives: the facts only, meaning totals, and group, category and merchant
    names. Data Status' texts name accounts and so people, so Claude gets only how many items
    are open. No account numbers, people's names or statement text.
- **Saved, not regenerated on every visit.** `core.monthly_report` (migration 0017) keeps one
  report per month: facts, findings, who wrote it and when. **Regenerate** replaces it after more
  statements are loaded.
- **Exports.** `GET /api/exports/{dataset}.{csv|xlsx}` with `month` or `year`.
  - Datasets: monthly cash flow (both views), categories by month, spending lines, interest and
    fees, and transactions with account and category path.
  - Yearly views asked for a month give that month's year.
  - CSV is UTF-8 with a byte-order mark so Excel reads accents.
  - Excel keeps real numbers (`#,##0.00`), real dates, a frozen header and a filter.
  - Links are on the Report page, and on Overview, Spending and Debt.

## Consequences

- The report is only as complete as the month. An incomplete month leads with what's missing,
  and regenerating after loading statements updates it.
- Without an API key the page still works: the findings are plainer but use the same facts.
- Each Claude report costs one call per regenerate, not per visit.
