# ADR-058: To do, one section at a time, and every task can be finished

Status: accepted (0.71.0, Nov 2026)

## Context

Hernan (Nov 9 2026) on To do: choosing a category on a transfer "does nothing"; there's no way to
add a person; he doesn't know what to do with out-of-date values, how to change or refuse a
suggested rule, or what the tax deduction invoices need; and he doesn't like how the page looks
and is organized. Behind "nothing happens": a transfer given Card Payment or Between Own Accounts
still has no other side, so it stayed in the list, and the confirmation showed at the top of a
long page. The transfers list (130) also held lines from workbook months, which count the
workbook's rows and need nothing, and Always made rules from texts like "TRANSFERENCIA INTERNET"
that would catch unrelated payments.

## Decision

- **Layout:** the sections are a list on the left (chips that scroll on phones) with how many
  things are left; one section shows at a time (its key in the URL hash), with a plain-words
  "what to do" box above its rows. A row: title and amount, a detail line with the statement
  link, then its actions. A finished row leaves the list; the confirmation is a toast at the
  bottom of the screen.
- **Transfers:** only months whose statements count (from `statements_from`), newest first.
  "Other side isn't in the app" settles a line on its own (a transfer group of one, logged; unlink
  asks again). Choosing a transfer category settles it the same way.
- **People:** "+ New person…" adds one and assigns the line in one step.
- **Rules:** "Use for future lines too" (was Always) is off, and explained, when every word of the
  description is general (TRANSFERENCIA, INTERNET, SU PAGO…). An existing rule isn't an error.
- **Values:** today's value and Save right in the row, or Stop counting it; an account valued from
  statements offers Upload its statement or Don't ask again.
- **Suggestions:** Save rule, the same rule with a different category, or No; bills: Add to bills
  or Not a bill. No and Don't ask again are remembered (`core.app_setting` keys
  `todo-dismissed:<hash>`), so they aren't asked again. No schema change.
- **Invoices** say what the deduction needs and open Tax deductions; the other links say what
  they do (Upload it, Review the import, See bills).

## Consequences

The transfers list shrinks to the months that matter, and every task has a way out. A settled
one-sided transfer still counts as a transfer, not spending; if its statement shows up later,
unlink it on the line and the two sides pair.
