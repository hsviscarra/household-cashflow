# Design system: Mercado

Chosen 2026-10-19 from three explored directions (canvas "Cash Flow App — UX directions").
Bright and friendly: a white ground, one color per spending category, rounded pill controls,
headlines that state the month in a sentence. Tokens live in `web/src/index.css`; use the
Tailwind utilities they generate (`bg-surface`, `text-muted`, `bg-primary`, `font-display`…),
never raw hex in components.

## Type

| Role | Family | Use |
|---|---|---|
| Display | Bricolage Grotesque 500/700 | Page titles, month headline, section titles |
| Interface | Figtree 400/500/600 | Everything else |
| Numbers | Figtree with `.num` (tabular figures) | Every amount, so columns line up |

## Color

| Token | Light | Dark | Use |
|---|---|---|---|
| ground | #FFFFFF | #17152B | Page background |
| surface | #F3F2F8 | #221F3D | Nav track, inputs, quiet panels |
| line | #E4E2EE | #34305A | Borders, dividers |
| ink | #241F45 | #EEEDF7 | Text |
| muted | #5D5880 | #ACA8C8 | Secondary text |
| primary | #2F5BEA | #8AA4FF | The one main button per screen, links |
| attention-bg / ink | #FFF4DA / #6B4A00 | #3A3014 / #F5D58A | Needs action: review, shortfall, interest |
| good-bg / ink | #E9F6F3 / #00695C | #12332E / #7FD8C8 | Confirmations, healthy status |
| danger-bg / ink | #FCE8E4 / #A3301B | #3B1C17 / #F4A898 | Discard, delete, failed checks |
| info-bg | #EEF2FF | #232A52 | Neutral highlight panels |

Dark mode follows the device setting (`prefers-color-scheme`).

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

## Shape and spacing

- Buttons, nav items and chips: fully rounded (`rounded-full`), height ≥ 44 px.
- Panels: `rounded-2xl` (20 px), tinted backgrounds (attention, info, good) instead of shadows.
- Page width up to `max-w-6xl`, 48 px side padding on laptop, 16 px on phone.

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
