# ADR-081: Claude's tax category for suppliers nobody classified

Status: accepted (0.90.0, Nov 2026)

Improvement plan, item A7. An invoice's SRI category for gastos personales (ADR-036) comes from a
person's choice, the supplier's rule, the line that paid it, or its products when they are mostly
food or pharmacy. The rest waited on Taxes for someone, though most are plain: a school is
education, a clinic is health, an electronics shop isn't deductible. (The other half of A7,
linking an invoice to its payment when exactly one line fits, already existed: ADR-066.)

Once a day, on the Gmail script's check-in (ADR-078), `gastos_suggest.autopilot` asks Claude
about the suppliers that still have an unclassified invoice this year (up to 40, largest first),
with each one's name and its five largest products. An answer at 90% or more (the autopilot
threshold, ADR-029) is saved as that supplier's rule, made by "claude (automatic)". Taxes shows
those invoices with "Claude's reading of this supplier: change it if it's wrong". A person's
choice on an invoice wins over it, and "every invoice from this supplier" replaces the rule.
Unsure answers save nothing; the invoice keeps waiting and is asked about again another day.

Only the supplier's name (a business) and product descriptions go to Claude. Nothing is filed
with the SRI: the totals are a projection a person reviews before the annex.
