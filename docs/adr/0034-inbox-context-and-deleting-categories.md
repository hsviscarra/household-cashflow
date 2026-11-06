# ADR-034: What a line was, and deleting a category

Status: accepted (0.50.0, Nov 2026)

## Context

In the Inbox a line showed a short date, the account and the bank's description, often just
"TRANSFERENCIA" or a code, which isn't enough to choose a category. The statement itself has more:
the posting date, the card used, a reference, and sometimes the sender or payee on the next line.
Separately, categories could only be hidden (Active off), never deleted, and it wasn't clear
that categorizing in the Inbox teaches the app for next time.

## Decision

- **Inbox lines** carry the posting date, the statement and the page the line is on. Each line
  shows its full date ("Wed, Jul 8, 2026") and **Open the statement, page N**, which opens the
  stored PDF at that page (`/api/statements/{id}/file#page=N`).
- **More details** loads `GET /api/transactions/{id}/source` (for a statement still waiting for
  approval, `GET /api/batches/{batch}/lines/{stg}/source`) and shows: dates, account with its last
  four digits, card, the kind of line on the statement, reference, notes, the statement's file name,
  period, page and line. It also shows the **statement text three lines above and below**, the
  line in bold, read from the stored PDF on request. Then the **transfer email** matched to the line
  (who sent it and the note), and up to five **earlier lines of the same merchant with the category
  they got**.
- Privacy: the text around a line is never saved, and any run of six or more digits (an account
  number, a cédula) is cut to its last four before it leaves the server. If the PDF can't be read,
  the facts still show and the page says so.
- **Deleting a category**: `GET /api/categories/{id}/uses` counts its lines, rules, bills,
  budgets and other links. `DELETE /api/categories/{id}` removes an unused one at once. A used one
  needs `move_to`, a category of the same kind. Its lines, rules, bills, people, holdings,
  transfer notes and staged lines move there, and budgets in the same month and label are added
  together. Every moved line gets a change-log row, then the category goes. A group goes once it
  has no subcategories. Settings has **Delete…** in each category's edit form. No migration.
- The Inbox says plainly that a category saved with "Use for this merchant from now on" (on by
  default) becomes a rule, and the next statements categorize that merchant on their own.

## Consequences

- Opening the PDF at a page depends on the browser's viewer (Chrome, Edge, Firefox and Safari
  support `#page=`); otherwise it opens at page 1.
- Each More details click reads one PDF (a fraction of a second); nothing is cached server-side.
- Deleting can't be undone with a button, but the change log keeps each line's old category.
