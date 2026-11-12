# ADR-085: To do that settles things, and a daily refresh

Status: accepted (0.94.0, Nov 2026).

Hernan, Nov 12 2026, working through To do: a rule he saved kept coming back as a suggestion; a
suggested category could only be accepted by choosing it again; "all from this supplier" left
the supplier's other invoices on the list; statements were asked for accounts the bank sync
already covers; and 26 bills were "not paid" on the 12th of the month.

## Decision

- **A rule saved from a merchant key matches.** To do, Review and rule learning save the merchant
  key as the rule's text, and the key drops numbers inside a description, so a "contains" rule
  such as `PRIME VIDEO * -802-` never matched the bank's text. A "contains" rule now matches the
  description or its key. The key function moved to the rule engine (`rules.key`), which owns
  matching; `classify.merchant_key` delegates to it. No rule had to be rewritten.
- **Rules reach waiting lines daily.** `classify.apply_rules` runs every active rule over the
  loaded lines without a category, first match by priority as in an import. The daily check-in
  calls it, so rules that start to match with this change categorize what was waiting.
- **Accept is one press.** A suggested category in "Needs a category" has an Accept button; a
  transfer that already has a category offers "Keep as …".
- **Invoices.** "All from this supplier" is on by default and sits before the choices. With it,
  whose the invoice is also goes to the supplier's other invoices of the year that are nobody's
  (no choice of their own, not paid by a line that says whose). An invoice paid by a line whose
  category is in no SRI group is "not deductible, from the line that paid it" instead of waiting.
- **Bank sync covers the days it asked for.** Coverage starts 44 days (the sync's look-back)
  before the first sync that reached the account, not at the first line it brought: a day with no
  movement is covered, not missing.
- **Only late bills in the current month.** A month that's over lists every unpaid bill; the
  current month lists those past their day, the same rule the Bills page uses for "late".
- **A daily refresh without opening the app.** The Gmail script's check-in (about 6 am) also runs
  the bank sync when one is due. `services/refresh.py` holds "sync, then people, transfers,
  invoices, bills and Claude's categories" for the app's open, Sync now and the check-in alike;
  the router no longer orchestrates it.
- To do links to Transactions → By category (ADR-065), the place to check what is already
  categorized.

## Consequences

- Rules whose text is a merchant key start matching; their lines are categorized at the next
  check-in, each change in `audit.change_log` with the rule as the reason.
- Invoices paid by a non-deductible line leave "need a category"; choosing a category on the
  invoice still overrides.
- No schema change. Whose a supplier's future invoices are is not remembered (that would need a
  column on `core.gp_issuer_rule`); only invoices already loaded are filled.
- The code-quality standard Hernan set is in the Definition of Done; shortfalls found in existing
  code are logged in `docs/refactors.md`, not rewritten here.
