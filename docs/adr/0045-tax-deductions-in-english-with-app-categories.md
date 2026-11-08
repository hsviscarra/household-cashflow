# ADR-045: Tax deductions in English, with the app's categories

Status: accepted (0.61.0, Nov 2026)

## Context

Hernan wants the app in English for now. The personal expense deductions page (ADR-036) was
titled "Gastos personales", labeled SRI's six groups in Spanish, and asked for one of those six
groups on each invoice: a different category list from the one used everywhere else.

## Decision

- The page is "Tax deductions" (nav and title); SRI's groups are labeled Food, Health,
  Education, arts & culture, Housing, Clothing and Domestic tourism; "cargas familiares" are
  dependents, IVA is VAT, "issuer" is supplier. The annex CSV headers are in English too. The
  stored keys (`alimentacion`, `salud`, …) stay as the SRI names them.
- Migration 0036 adds `core.invoice.category_id`. On the page each invoice takes an app category
  from the same category picker as the rest of the app; its SRI group follows from that category
  (or its group) through the existing map, and a category that maps to none is not deductible.
  The row shows "Deducts as Health" or "Not deductible". Choosing an SRI group directly (API
  only) clears the app category. Deleting a category moves invoices with the rest of its uses.
- An invoice without a category of its own shows the paying line's category, as before.

## Consequences

- One category list across the app; SRI groups are something the app works out, not something
  to choose. Category names Hernan created in Spanish stay as he named them.
