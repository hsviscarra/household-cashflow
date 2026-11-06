# Design system: Ledger

Chosen 2026-11-05 (ADR-025) to replace Mercado, from the redesign canvas "Household Cashflow
redesign". Calm and dense: a dark sidebar, a light grey canvas with white cards, KPI tiles at the
top of every page, one color per spending category, rounded pill controls. Tokens live in
`web/src/index.css`; use the Tailwind utilities they generate (`bg-canvas`, `bg-ground`,
`text-muted`, `bg-primary`, `font-display`…), never raw hex in components.

## Type

| Role | Family | Use |
|---|---|---|
| Display | Space Grotesk 500/600/700 | Page titles, section titles, KPI numbers |
| Interface | Inter 400/500/600/700 | Everything else |
| Numbers | Inter with `.num` (tabular figures) | Every amount, so columns line up |

## Color

| Token | Light | Dark | Use |
|---|---|---|---|
| canvas | #F6F7F9 | #0B1220 | Page background |
| ground | #FFFFFF | #121B2C | Cards, inputs, secondary buttons |
| surface | #EBEEF3 | #1A2539 | Quiet panels and tiles inside the page |
| line | #E3E6EC | #2A3650 | Borders, dividers |
| ink | #101828 | #E6EAF2 | Text |
| muted | #5B6474 | #A3AEC2 | Secondary text (≥ 5.3:1 on canvas, ground and surface) |
| primary | #2B4ACB | #8AA4FF | The one main button per screen, links |
| attention-bg / ink | #FEF3C7 / #5A3B00 | #3A2F10 / #F5D58A | Needs action: inbox, shortfall, stale values |
| good-bg / ink | #E7F6F3 / #0B6B5E | #10302B / #7FD8C8 | Confirmations, healthy status |
| danger-bg / ink | #FDE7DF / #9A3412 | #3B1D14 / #F4A898 | Discard, delete, failed checks, shortfalls |
| info-bg | #EEF2FF | #1C2650 | Neutral highlight panels |
| nav / nav-ink / nav-muted / nav-active | #0F1B2D / #C9D2E0 / #8E9AB0 / #22324D | #070D18 / … / #1A2539 | The sidebar |

Dark mode follows the device setting (`prefers-color-scheme`). Every text pair above passes WCAG AA.

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
