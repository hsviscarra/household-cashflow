# ADR-047: One To do list

Status: accepted (0.62.0, Nov 2026)

## Context

Hernan: "I feel that I have to do work everywhere and I am losing track of all the things I have
to do." Lines to categorize lived in the Inbox, missing statements and imports on Data status,
out-of-date values on Net worth, suggested rules in Settings, found bills on Recurring and
invoices on Tax deductions. Transfers from his employer could only be given a person, not
called Salary.

## Decision

- `GET /api/todo` gathers it all in sections, each task with its kind, title, detail, amount,
  date, link and the data the page needs to act on it; `total` counts everything, also past the
  first 25 tasks a section shows:
  1. **Needs a category**: merchants with uncategorized lines (most lines first).
  2. **Who or what is it**: transfers that don't say who (the Inbox's Who list). Asked once:
     these lines are left out of section 1.
  3. **Statements, imports and bills**: Data status for the last 3 months, without this month's
     statements (not issued yet) and without what sections 1, 2 and 4 list.
  4. **Transfers missing the other side**.
  5. **Out-of-date values**, with old workbook rows next to a real account marked as probably
     the same money twice (the Net worth page's freshness rule, kept in step).
  6. **Suggestions**: rules suggested from hand choices (ADR-042) and bills found (ADR-043).
  7. **Tax deduction invoices** to sort out this year.
- The To do page acts in place: a category picker with **Always** (a rule) for merchants; for a
  transfer, a person or a category (with Always); Pause it for a duplicate value; Save rule; Add
  to bills; everything else opens the page where it's fixed. A finished task drops off.
- A transfer given an income or expense category (Salary from Kenility) no longer needs a person,
  so it leaves the Who list.
- The sidebar shows To do under Home with the total; Inbox and Data status leave the sidebar
  (still reachable by address and from To do). Home's "Needs you" strip shows To do's sections.

## Consequences

- One place to work through, with a count that only goes down as things get done.
- The page asks the server for everything at once; the sidebar count reuses it for 5 minutes.
- 0.68.1: transfers missing the other side take a person or a category in place (a house or loan
  payment made by transfer), like the Who list.
