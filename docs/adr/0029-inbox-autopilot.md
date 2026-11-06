# ADR-029: The Inbox does more of the work

Status: accepted (0.45.0, Nov 2026)

## Context

The redesign's fifth PR (ADR-025). Statements now approve on their own (ADR-024), but every
new merchant still needed a visit to the Inbox, one card at a time, even when Claude was sure;
and transfers that only say "TRANSFERENCIA" had nowhere to be told who they were for.

## Decision

- **Autopilot**: right after a statement is approved on its own (and after "Approve all that
  tie out"), Claude is asked about merchants without a suggestion and every suggestion at or
  above **`AUTO_ACCEPT_CONFIDENCE`** (default 0.90; 0 turns it off; needs `ANTHROPIC_API_KEY`)
  is accepted with a rule, exactly as a click would, but recorded as "(automatic)" in the change
  log. Anything less sure waits in the Inbox. A failure (Claude down) is logged and changes
  nothing.
- **Accepted on their own**: the Inbox lists the rules autopilot saved in the last 30 days with
  their lines. **Undo** turns the rule off and puts each line back as it was before (category
  and type from the change log); lines a person changed since are left alone.
- **Many at once**: select merchants (or all) and either accept their suggestions or give them
  one category, each with a rule (`POST /api/review/resolve-many`).
- **Keyboard**: j/k or ↓/↑ move between merchants, a accepts the suggestion, c opens the
  category, x selects, ? shows the keys; keys typed in a field are left alone.
- **Who was it for?**: statement lines whose description says a transfer happened
  (TRANSF, ZELLE, INTERBANC, SPI, PAGO DIRECTO, DEPOSITO, ...) but have no person, from the last
  90 days, leaving out card payments and transfers between your own accounts. Picking a person
  sets it, and their category unless someone chose one (as a person's text would, ADR-023).
- Endpoints: `GET /api/review/auto`, `POST /api/review/auto/{rule_id}/undo`,
  `POST /api/review/resolve-many`, `GET|POST /api/review/who`; `approve-ready` also reports
  what autopilot did.

## Consequences

- No schema change: autopilot's work is found through `audit.change_log`.
- Rules from autopilot are ordinary rules; turning one off on Undo keeps it visible on the
  Rules page.
- The 0.80 "Accept likely suggestions" button stays for the suggestions between 0.80 and 0.90.
