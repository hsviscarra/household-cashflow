# ADR-024: Automatic approval of statements that tie out

Status: accepted (0.39.0, Nov 2026)

## Context

Every statement waited on the Import page for a click, even when every check passed: lines add up
to the statement's totals, the opening balance equals the previous statement's closing balance,
and every line was read. With statements arriving by email (ADR-020) and in batches of uploads,
the click was routine work that added nothing.

## Decision

- **When:** a batch is approved on its own when it ties out (`tieout_ok`: totals and continuity)
  and the parser left no line unread (`rej.rejected_line`). Lines without a category don't hold
  it back: they go to Review like any other.
- **Where:** right after a statement is read: by the Gmail script's inbox (in the background),
  after an upload (uploads are now read in the background straight away), and after Read on the
  Import page.
- **Who:** `decided_by` is the uploader followed by "(automatic)", so the audit trail tells the
  two apart.
- **Everything else waits** on the Import page with its reason. "Approve all that tie out"
  approves the waiting backlog in one call, oldest period first, and lists what still needs a
  person.
- **Off switch:** `AUTO_APPROVE=false` brings back read and approve by hand (the tests and the
  end-to-end run use it to exercise the manual path).

## Consequences

- A wrong parser result that still ties out is approved without a look; the tie-out and continuity
  checks are what stand behind it, as they already did for the click.
- An approved batch can't be undone from the page; a wrong line is fixed on Transactions.
