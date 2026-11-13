# ADR-103: Services split into named steps and modules

Status: accepted (0.112.0, Nov 2026). No schema change, no change in what the app does.

## Context

ADR-102 put limits on function size under CI and left 32 functions as a written baseline. Twenty
of them were in the services (`status.month_status`, `recurring.bills` and `match`,
`report.rule_findings`, `shopping.ideas`, `digest.build`, `iva.workbook` and others), and two
service modules held several subjects each: `status.py` (about 900 lines) and `recurring.py`
(about 1,300).

## Decision

- **Each long function is now a short one that names its steps.** Three shapes were used:
  - a list of rules or sections, each a small function that returns its result or nothing
    (`report.RULES`, `digest.SECTIONS`, `shopping.ideas`): adding a finding, a section or an
    idea is adding one function to a list;
  - a small object that carries what the steps share (`recurring._Links`, `status._Known`,
    `groceries._Tally`, `gastos._Evidence`, `iva._Sheet`);
  - validation moved out of the function that writes (`_checked_changes`, `_copy_range`,
    `_checked_share`, `_patterns`).
- **`recurring` and `status` are packages.** `recurring`: `base` (months, amounts over time),
  `templates`, `matching`, `year_grid`, `bill_list`. `status`: `base` (what it is made of),
  `arrival` (how each account's data arrives), `statements` (coverage and timelines), `months`
  (what each month needs). The package re-exports the same functions, so callers still write
  `recurring.bills(...)` and `status.month_status(...)`.
- **Dependency direction.** What decides whether a rule on a description is safe, and the
  priority of a rule saved while reviewing, belong to the rule engine (`rules.rule_ok`,
  `rules.REVIEW_RULE_PRIORITY`); modules that only needed a merchant's key ask the rule engine,
  not `classify`. Thirteen imports inside functions became ordinary imports. In the services two stay, each with
  its reason beside it: `transfers` and `classify` need each other, and the models register the
  flush listeners.
- **Numbers named** on the way: 36 months a copy, 1,000 ids an `IN`, the 7 days of "bills this
  week", the 4 letters a text to find needs.

## Consequences

- The baseline is down to 12 functions, all in reading statements and the workbook; they are
  the next change, one parser at a time.
- Behaviour is the same by construction; the checks are the existing unit, integration and
  end-to-end tests and a comparison of the live pages before and after.
