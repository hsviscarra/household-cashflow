# ADR-102: The code standard is enforced by the linters

Status: accepted (0.111.0, Nov 2026). No schema change, no change in what the app does.

## Context

The Definition of Done carries a code standard (SOLID and layering, typed, no unexplained
warnings, no magic numbers, specific exceptions, docstrings, small functions). It was checked by
reading, and reading missed things: 17 copies of the same `_user(request)`, broad `except
Exception` around network calls with no retry, hundreds of public functions and classes with no
docstring, and functions of 80 statements.

## Decision

What a tool can check, CI checks; a rule that fails stops the merge.

- **API (ruff).** Added to the rules: `D1` (every public module, package, class, function and
  method has a docstring), `BLE` and `S110` (no blind `except Exception`, no silent `pass`),
  `C90` with a complexity of 10 and `PLR0915` with 50 statements a function. Tests and
  migrations are exempt from the docstring and size rules.
- **Web (ESLint).** `max-lines` of 400 a source file (comments and blank lines not counted);
  tests exempt.
- **Baselines, written down.** 32 existing functions (the parsers above all) carry
  `# noqa: C901 - baseline, docs/refactors.md #15`, and 23 existing web files are listed as
  `BASELINE` in `eslint.config.js`. The parsers are guarded by tie-out and golden tests and
  are the code where a careless split costs most, so they are split one at a time, each as its
  own change. Nothing new joins either list.
- **Outside calls** go through `app.outside`: the errors a network or storage call can raise,
  named, and `retry` (three tries, the wait doubling) around the bank sync's request.
- **Who is asking** is one function, `app.auth.current_user`, for every router.
- **Done in this change, as the example:** `projections.project` (complexity 23, 87 statements)
  is now seven named steps; the Saving page's debts section is its own file.

## Consequences

- A new function without a docstring, a new broad `except`, a function that grows past the
  limits or a web file past 400 lines fails CI.
- What a tool can't check (layering, dependency direction, naming, whether a docstring says
  why) is still a matter of review; `docs/refactors.md` lists what is open.
