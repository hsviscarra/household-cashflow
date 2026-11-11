# ADR-077: Claude categorizes on arrival, with what the app already knows

Status: accepted (0.86.0, Nov 2026)

First step of the improvement plan Hernan approved on Nov 11 2026 (phase 1, items A1 and A2). His
decisions: Claude may apply a category by itself at 90% or more, with the log and undo of ADR-029;
the request may include invoice product names and whose line it is.

**On arrival (A1).** Autopilot (ADR-029) ran only after a statement was approved, so lines from the
daily bank sync (ADR-044) got rules and nothing else, and a new merchant on Bank of America or
Capital One waited for a person. `POST /api/bank-sync/run` now runs autopilot after its other
follow-ups when lines were added, and answers with `auto: {merchants, lines}`. Sure suggestions
are applied with a rule and listed under "accepted on their own", where one click undoes them;
the rest wait in the queue with the suggestion pre-filled.

**With context (A2).** Claude saw the description, amounts, dates and the bank. Each merchant now
also carries `context`, built from what Transactions shows for one line (ADR-074):
- `person`: whose line it is (Hernan, Lauren, Juliana);
- `card_purpose`: what the card is kept for and its usual merchants;
- `same_amount_before`: up to 3 earlier lines of exactly that amount from another merchant, with
  their category (a repeating amount is usually the same bill);
- `invoice`: the seller and up to 5 products of an electronic invoice of that amount within 5 days.

The request also carries `examples`: the 25 most recent categories chosen by hand, one per
merchant, so Claude follows the family's way of categorizing.

Consequences: more leaves the server than before (person labels, invoice sellers and products,
descriptions of earlier lines); still no account numbers, balances or cédulas. Requests are a
little longer; the model and the 0.90 threshold are unchanged.
