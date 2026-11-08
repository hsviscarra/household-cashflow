# Design system: Clear

Chosen 2026-11-06 (ADR-035) to replace Ledger, from the "Look A: Clear" board of the canvas
"Household Cashflow redesign". The layout, sidebar groups and pages of ADR-025 stay; the look is
brighter and higher in contrast: a white page, a light sidebar, near-black text, one green
accent, 10 px corners on controls and 14 px on cards. Tokens live in `web/src/index.css`; use the
Tailwind utilities they generate (`bg-canvas`, `bg-ground`, `text-muted`, `bg-primary`,
`font-display`…), never raw hex in components.

## Type

| Role | Family | Use |
|---|---|---|
| Display | Plus Jakarta Sans 700/800, tight tracking | Page titles, section titles, KPI numbers |
| Interface | Plus Jakarta Sans 400/500/600 | Everything else |
| Numbers | The same with `.num` (tabular figures) | Every amount, so columns line up |

## Color

| Token | Light | Dark | Use |
|---|---|---|---|
| canvas / ground | #FFFFFF / #FFFFFF | #0C0D10 / #15171C | Page; cards, inputs, secondary buttons |
| surface | #F2F4F7 | #1C1F26 | Quiet panels, bar tracks |
| line / line-strong | #E4E7EC / #D0D5DD | #2A2D35 / #3A3E48 | Card borders / control borders |
| ink | #0B0F19 | #F5F6F7 | Text (≥ 18:1 on white) |
| muted | #475467 | #A9AEB8 | Secondary text (≥ 7:1 on white, ≥ 7:1 on dark cards) |
| primary | #047857 | #34D399 | The one main button per screen, links, Inbox count |
| attention-bg / line / ink | #FFFAEB / #FEDF89 / #7A2E0E | #2A2210 / #5C4A1A / #FCD889 | Needs action |
| good-bg / ink | #ECFDF3 / #05603A | #13291C / #86EFAC | Confirmations, healthy status |
| danger-bg / ink | #FEF3F2 / #B42318 | #331716 / #FCA5A5 | Delete, failed checks, shortfalls |
| warn | #DC6803 | #F59E0B | A budget bar running ahead of pace (never text) |
| info-bg / ink | #EFF8FF / #175CD3 | #16223A / #93C5FD | Neutral highlight panels |
| flow-in / flow-out | #047857 / #175CD3 | #34D399 / #60A5FA | Money in / out in charts (green / blue, told apart by lightness too) |
| nav / nav-line | #F7F8FA / #E4E7EC | #0C0D10 / #24262D | The sidebar and its hairline |
| nav-ink / nav-muted / nav-strong | #344054 / #667085 / #0B0F19 | #B4B9C4 / #8A909C / #F5F6F7 | Links, group names, hover and brand |
| nav-active / nav-active-ink / nav-well | #E7F5EF / #05603A / #ECEFF3 | #13291C / #86EFAC / #1C1F26 | The current page; the person switch's well |

Dark mode follows the device setting (`prefers-color-scheme`). Every text pair above passes WCAG AA;
body text passes AAA.

## Navigation (ADR-025)

A left sidebar (a menu button on phones and tablets) with the pages in groups: Home · Analyze
(Spending, Purchases, Net worth) · Daily (Inbox, Transactions, People & transfers) · Plan
(Bills, Subscriptions, Forecast) · Reports (Monthly report, Data health, Import); Upload
statements, Settings, who's signed in and the database status at the bottom. The Inbox shows
how many lines wait for a category. URLs stay as they were.

## Personal settings (ADR-026)

- The Both / Hernan / Lauren switch sits at the top of the sidebar as a segmented control
  (radio buttons). A page that follows it says so when one person is shown ("Showing Lauren's
  lines only. Show both").
- Tables with a column chooser put "Columns & rows" and "Save view" at the right of their
  filters. Compact rows halve the vertical cell padding; nothing else changes size.
- Saved views are listed in the sidebar under "Saved views", each with a remove (×) button.

## Cash flow charts (ADR-027)

- **Sankey**: money in (flow-in) on the left, the month as an ink bar in the middle, money out
  on the right in each group's color, "Left over" in flow-in. Bands at 28% opacity; a node is
  at least a label tall; more than nine nodes on a side fold into "Other". Each band is a
  button that opens its group or category.
- **Waterfall**: last month (muted), the changes (flow-in when good, danger ink when not:
  more money in is good, more money out is not), this month (ink).
- **Home widgets** are cards in two columns (Needs you and the numbers span both); Customize
  lists them with up, down and hide.

## Spending (ADR-028)

- **Treemap**: blocks in each group's color with white text, 10px radius, a 2px ground gap;
  label, amount and line count when the block has room. Each block is a button.
- **View switch**: a segmented control (Groups, Merchants, Products, Fixed vs variable) at the
  right of the month controls.
- **Ways to save**: the amount in good ink on the left, the title in bold, the detail muted and
  a "Look →" link.

## Inbox (ADR-029)

- The autopilot panel is a surface box at the top: one bold sentence saying whether it's on,
  then the rules it saved with an Undo button each.
- A selection bar sticks to the top while scrolling: select all, accept suggestions, one
  category for all. A selected card gets a primary border and a light info background.
- Keyboard shortcuts are listed behind a "Keyboard" link (and "?"), never only in a tooltip.

## Transactions (ADR-030)

- Saved views are tabs under the title: a 2px primary underline marks the current one.
- Filters sit in one wrapping row of labelled fields; Save view and Columns go at its end.
- A line's person is a muted pill linking to their lines; the note follows in muted text.
- The footer under the table: lines shown and money out on the left, "Total shown" on the right.

## Bills (ADR-031)

- Calendar cells are bordered, Monday first, today ringed in primary. A bill is a small chip:
  good background when paid, surface when due, danger background when late, info background
  with ↑ for money in. Status is also in the chip's text for screen readers, never color only.
- On phones the calendar becomes a list by day.

## Net worth (ADR-032)

- Freshness is a small badge after the date: good background "up to date", attention
  background "out of date · N days".
- A possible duplicate is one attention-ink line under the item with an underlined action.
- The what-if sits in a surface box inside the loan's card.

## Forecast (ADR-033)

- The cash chart draws the total as a solid primary line and each account dashed in its own
  color, with a legend under it; the floor is a dashed danger line, zero a muted line.
- The heads-up is an attention box listing each account under the floor with the amount and the
  date to move it by; segment switches (horizon, months to average) use `aria-pressed`.
- The ten answers are cards in two columns: the question small and muted, the answer large in
  the display font, colored good or attention by tone (never color only: the sentence says it).

## Inbox details (ADR-034)

- A line's date is written in full; "Open the statement" and "More details" are small underlined
  primary links under it. Details sit in a surface box: facts as a two-column list, the
  statement's text in monospace on the ground color with the line itself in bold, the transfer
  email in an info box.
- Delete lives inside the edit form as a quiet button in danger ink; the confirmation is a
  bordered box that says what moves where, never a browser dialog.

## Tax deductions (gastos personales, ADR-036)

- One card per person: the rebate as the KPI in primary, what counts toward the cap with a
  primary bar on a surface track, then the six categories as a plain table and the cargas form.
- Invoices sit in one bordered list; whose and the category are inline selects that save on
  change, with the reason for a guess in muted text under the issuer.

## SRI list import (ADR-037)

- "Upload the SRI list (.txt)" is a secondary button beside "Upload invoice XMLs"; "Paste access
  keys" is a quiet button that opens a full-width textarea. While it runs, the button says how
  far it got ("Getting 20 of 45 from the SRI…"); the outcome goes in the page's status line and
  the results list.

## Budget (ADR-039)

- One card per group: name with its color dot, a status pill (Over in danger, Ahead of pace in
  attention, On track in good, No budget muted), "spent of available", then a bar on a surface
  track in primary, warn or danger-ink with a thin ink mark at today's share of the month.
- Changing a budget opens an inline form in the card (amount from this month on, rollover).

## Goals (ADR-040)

- A card per goal in two columns: name, where the money is and the date in muted text, a status
  pill (Reached and On pace in good, Behind in attention, Date passed in danger, No date muted),
  saved of target as a display number, a bar in primary (warn when behind or late) and one pace
  sentence. Paused goals show at 60% opacity.

## Suggested rules (ADR-042)

- A card above the rule list, shown only when there are suggestions: pattern in mono, then the
  category, person, times and an example in muted text; Save rule (primary) and Not now (quiet),
  both small (h-9). Rules that also set a person or name say so in muted text under the category.

## Found bills (ADR-043)

- A card under the Recurring actions, shown only when something is found: name in semibold, the
  amount in tabular numerals, a pill for how often; category, account, usual day and charges in
  muted text; Add (primary) and Not now (quiet), both small (h-9).

## Bank sync (ADR-044)

- Settings tab: a card with the last sync, the pending count and Sync now (primary); SimpleFIN
  errors as warn-bordered alerts; a table of bank accounts (org in semibold, balance in tabular
  numerals) with a select of the app account each feeds.

## Tax deductions (ADR-045)

- Each invoice row uses the shared CategoryPicker (label hidden, "Category for <supplier>") and a
  pill with what it deducts as; muted when not deductible or not known yet.

## KPI tiles

`components/KpiCard`: label (small caps, muted), the value in the display face, an optional note
or change (good / bad tone) below; the attention tone fills the tile. A row of 3–5 opens a page.

### Category colors

Each category keeps its color everywhere: bars, chips, dots, legends. Always show the category
name next to its color; color is never the only signal.

Colors are stored per category group in `core.category.color` (seed v1 below) and editable on
Settings → Categories. Subcategories use their group's color.

| Group | Color | Group | Color |
|---|---|---|---|
| Housing | #6B6788 | Transport | #3AA7D9 |
| Utilities | #8D6E63 | Subscriptions & Software | #2F5BEA |
| Household Staff | #7B4BD6 | Shopping | #C2185B |
| Childcare | #E57BA9 | Travel | #E8A000 |
| Health | #00897B | Donations | #9C8D2B |
| Groceries | #4E9A2A | Financial Costs | #A3301B |
| Dining | #E2583E | Savings & Debt | #1E3FB0 |

Income groups reuse the same hues (Salary #4E9A2A, Office Rent #00897B, Insurance
Reimbursement #3AA7D9, Interest Earned #7B4BD6, Other Income #6B6788); Transfers have no color
because they never appear in spending charts.

New categories get a color from this list's unused hues or `muted` until one is chosen.

## Charts

- Money in / out: `flow-in` #0E8F7E (dark #2BB39F) and `flow-out` #7A5AF0 (dark #9B84F5). Trends with one series use `primary`.
- Columns at most 24 px wide with 4 px rounded tops, 2 px apart; lines 2 px; hairline solid grid;
  axis ticks compact (5K). A legend whenever there are two or more series; plan values at 35%
  opacity with "Plan" in the legend.
- Every chart has a hover or focus tooltip and a table with the same numbers on the page.
- Text never takes the series color; identity comes from the swatch beside it.

## Shape and spacing

- Buttons, nav items and chips: fully rounded (`rounded-full`), height ≥ 44 px.
- Cards: `.card` (white, `rounded-2xl`, hairline border) on the canvas; tinted backgrounds
  (attention, info, good) for status instead of shadows.
- Content width up to `max-w-7xl` next to the 240 px sidebar; 40 px side padding on laptop, 16 px on phone.

## Buttons

| Kind | Look | Example |
|---|---|---|
| Primary | `bg-primary text-on-primary` | Upload statements, Approve import |
| Secondary | outlined, `border-line` | Edit category |
| Destructive | `bg-danger-bg text-danger-ink` | Discard batch |

One primary per screen. Labels say what happens; the confirmation repeats the words
("Approve import" → "Import approved").

## Behaviour

- **Navigation:** pill menu across the top; on a phone it scrolls sideways. One month picker for the
  whole app; every number links to the transactions behind it.
- **Money:** USD, two decimals, thousands separators, no symbol in tables. Spending in ink, not
  red; income with a +; amber only for "needs action"; expected money shown as expected.
- **Import:** upload → check (tie-out, continuity) → review (only what needs a decision) →
  approve. Nothing is saved before Approve.
- **Editing:** inline category edits with "apply to this merchant from now on", history kept,
  Undo after each change, split a charge across categories.
- **Empty and error states:** say what happened and what to do, with the action button.
- **Phone:** upload, review an import, check the month. Laptop adds the recurring grid, bulk
  edits and exports.
- **Accessibility:** text contrast ≥ 4.5:1, visible focus ring (`primary`), real buttons and links,
  labels on every input, category names beside colors.
