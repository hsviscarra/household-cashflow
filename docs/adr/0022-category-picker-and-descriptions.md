# ADR-022: One category picker, with descriptions, that can add a subcategory

- Status: accepted
- Date: 2026-11-03

## Context

F23: categorizing was the slowest part of loading a month. Every screen used a native dropdown
with 70-odd "Group / Sub" entries, so finding one meant scrolling. Nothing said what belonged
where (Media or Apps for a Google Play charge? Bank Fees or Credit Card Interest?). A missing
category meant leaving the page for Settings. And Claude's suggestions only saw category names,
so they guessed on exactly the ambiguous cases.

Hernan's decisions (2026-11-03): Claude drafts a description for every category and he edits
them; the picker can create subcategories only, while a new group is a deliberate extra step;
"Other Expenses" (seed v2) is where an unsure line waits.

## Decision

- **`core.category.description`** (NVARCHAR(400), migration 0023). Seed v5 holds a drafted
  description for every seeded group and subcategory, written from the merchants the seeded rules
  already map. The migration fills only empty descriptions, matched by path, so a category
  renamed in the app is left for Hernan. Settings → Categories shows each description and edits
  it.
- **`GET /api/categories`** also returns, per category, `lines` (loaded lines) and `rules`
  (merchant rules pointing at it).
- **One `CategoryPicker`** (an ARIA combobox) replaces the dropdown on Review, Transactions (edit
  and split), Settings → Merchant rules and Recurring:
  - typing filters by group, subcategory and description, ignoring case and accents ("cafe" finds
    Cafés, "taxi" finds Rideshare through its description); names that start with the text come
    first;
  - with nothing typed it lists the five most used (by lines, then rules), then every category
    in the Settings order, with its group's color;
  - the highlighted option shows its description, and so does the field once one is chosen. This
    is the "tooltip": it works on a phone, where there is no hover;
  - arrows, Enter and Escape work, and Enter never submits the surrounding form.
- **Creating from the picker.** When the text matches nothing useful, "+ Create … as a
  subcategory" opens a small panel: name, group (preset to the group of the best match) and an
  optional description. "No group fits? Create a group…" is one step further on purpose: it says
  that groups shape every report, then takes a name, what it counts as, and an optional first
  subcategory. Either way the new category is chosen at once. The panel isn't a nested form, so
  it works inside Review's form.
- **Claude reads the descriptions.** Each category offered to the suggestion call carries its
  description, and the system prompt says to follow it over the general meaning of the word.
  Descriptions are Hernan's own text about categories, so no personal data is added to the
  request.

## Consequences

- Descriptions are data, not code: Hernan's edits survive later migrations, since seed v5 only
  fills empty ones.
- The picker loads the category list once (React Query cache) and reuses it on every page.
- Next (F23 part 3): Settings → Categories with search, counts and moving a subcategory to
  another group.

## Part 2 (0.28.0): categorize before approving, accept suggestions in one click

- **A statement's page** has a "Needs a category" section: its uncategorized lines grouped by
  merchant, with the same cards as Review (`GET /api/batches/{id}/review`). Categorizing there
  (`POST /api/batches/{id}/resolve`) sets the staged lines. Saving a rule (on by default) also
  reaches loaded lines and the other waiting statements, as in Review (#74). A merchant can
  still be left for Review after approval.
- **`stg.stg_transaction.category_source`** (migration 0024) records "manual" or "suggestion",
  so the loaded line says who chose its category instead of "by rule". Lines it doesn't mark
  keep the old derivation (rule, or the statement's section).
- **Claude for one statement:** `POST /api/batches/{id}/suggest` asks about that statement's
  merchants without a suggestion. Suggestions stay keyed by merchant, so Review sees them too.
- **One click.** A suggestion shows a "✓ Use …" button that saves it, with the rule if that box
  is on. "✓ Accept N likely suggestions" (`POST /api/review/accept-suggestions` and
  `/api/batches/{id}/accept-suggestions`) accepts every suggestion at 80% or more ("likely",
  the same word the cards show) and saves a rule for each. The rest wait for a person.
- The cards and the two Claude buttons are one shared component (`MerchantReview`) on both
  pages.
