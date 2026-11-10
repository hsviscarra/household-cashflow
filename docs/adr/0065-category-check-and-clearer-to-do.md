# ADR-065: Check every category in one place; clearer To do; true statement order

Status: accepted (0.77.0, Nov 2026)

## Context

Hernan (Nov 10 2026): there's no clear place to check all categories and recategorize; he
doesn't understand what a bill is, what "Add to bills" or "Not a bill" do, what "Statements,
imports and bills" means, or how to handle suggested rules. Data status also showed three balance
breaks (Bank of America, Pichincha) that weren't breaks: the same statement period uploaded as
two files was compared with itself. Groceries didn't load for him.

## Decision

- **Transactions → By category** (`/transactions/categories`, a tab of Transactions): every
  category of a month, 3 or 12 months, grouped as To do (no category), Income, Spending, Savings,
  Debt payments and Transfers, with its total and line count; its lines with a "Move to" picker
  each, and ticked lines moved together. Each move is a normal line edit (change log).
- **To do wording:** "Statements, imports and bills" explains the three kinds of loose ends; the
  suggestions box explains what a rule and a bill are and what saving or refusing does; rule
  suggestions read `Lines with "UBER" → Taxi`, bills "every month, around day 5 · seen 3 times".
- **Balance breaks** compare a statement with the latest one that ends before it starts, so the
  same period twice (or overlapping ranges) isn't a break.
- Groceries loads every invoice's lines in one query (selectinload) instead of one per invoice.

## Consequences

By category reads the same lines as Transactions, so a period with thousands of lines is as slow
as that page.
