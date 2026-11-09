# ADR-063: Property and vehicle values count back in time; every line through Claude

Status: accepted (0.75.0, Nov 2026)

## Context

Net worth history jumped from about −21,000 in September 2026 to +458,000 in October, only because
the department, office, house and car values were first entered on Oct 28: before that date
they had no value. Separately, Claude's read-only tools (ADR M8) only listed spending lines, so
a number like September's −14,500 of savings couldn't be traced from a conversation.

## Decision

- A property or vehicle with no value on or before a date uses its first value (it was owned
  before the value was entered). Investments, cash, loans and purchases still start when their
  first value does.
- The MCP tool **month_lines** lists a month's counted lines of any type (income, savings,
  debt payments, transfers…), or every line holding a text a month around.

## Consequences

Net worth history shows real changes; a property bought later than its first entered value
still appears earlier, so enter the purchase date's value when it matters.
