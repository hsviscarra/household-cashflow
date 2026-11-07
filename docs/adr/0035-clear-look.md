# ADR-035: The Clear look

Status: accepted (0.51.0, Nov 2026)

## Context

After the redesign (ADR-025 to ADR-033) Hernan liked how the app is organized but not its colors,
contrast or fonts: grey text on a grey canvas read washed out, the navy sidebar felt heavy and
Space Grotesk didn't fit. Three looks were drawn on the same Home page (Clear, Night, Banker) on
the redesign canvas; he chose **Clear** on Nov 6, 2026.

## Decision

- Only the look changes; the layout, navigation, pages and components stay.
- Plus Jakarta Sans for everything (display 700/800 with tight tracking), loaded from Google Fonts.
- A white page and cards, a light sidebar with a hairline, near-black ink and a darker muted grey
  (≥ 7:1). One accent, green #047857: primary buttons, links, the current page and the Inbox count.
- Money in is green and money out blue in charts, so they differ in lightness as well as hue.
- Controls and fields take 10 px corners instead of pills; cards 14 px. Chips stay pills.
- Dark mode is re-tuned to match (near-black page, mint accent). New tokens `line-strong`,
  `attention-line`, `info-ink`, `nav-line`, `nav-active-ink` and `nav-well`.

## Consequences

- Category colors change only where they clashed with the new accent (groceries, health, dining,
  subscriptions); users' own category colors are untouched.
- Screens in older runbooks and screenshots show the Ledger look until they are retaken.
