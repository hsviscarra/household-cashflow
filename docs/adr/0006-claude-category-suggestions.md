# ADR-006: Claude suggests categories; Hernan decides

- Status: accepted
- Date: 2026-10-26

## Context

Merchant rules categorize most statement lines, but every month brings merchants no rule knows
(new shops, Zelle payments, bank transfers). F9 resolves them in one review screen. The plan
(project instructions) calls for Claude to suggest a category with a confidence for those
merchants, never as the source of truth.

## Decision

- **Model and call:** the API calls the Claude API server-side with `claude-haiku-5-5` (built for
  classification; about $0.10 per million input tokens). One request covers up to 40 merchants of
  the review queue. The answer must follow a JSON schema (`output_config.format`, structured
  outputs) whose `category_path` is an enum of Hernan's own leaf categories and whose
  `merchant_key` is an enum of the merchants asked, plus a confidence (0–1) and a short reason.
  The model is configurable (`ANTHROPIC_MODEL`).
- **What leaves the server:** per merchant, up to three lines with the description as printed,
  amount, date, the bank's name and country and the account kind. No account numbers, no names
  of the household's people, no balances, no files. Descriptions can contain a payee's name
  (Zelle, transfers); that is the merchant itself.
- **Nothing is applied automatically:** suggestions are stored in `core.merchant_suggestion` and
  shown in the review queue with their confidence ("likely, 85%"). A line is categorized only when
  Hernan saves it; the line then records `category_source = 'suggestion'` and the change log says
  so. Saving usually also saves a rule, so the merchant never needs Claude again.
- **Key:** `ANTHROPIC_API_KEY` is a Container Apps secret in Azure (Bicep parameter
  `anthropicApiKey`, kept by `bootstrap.sh` re-runs) and an optional line in the local `.env`.
  Without it the review queue works and says suggestions are off.

## Consequences

- Cost is cents a month; a Claude outage only disables suggestions (the API answers 502 with a
  clear message).
- Merchants already suggested aren't asked again until the suggestion is used or removed.
- If a future feature sends whole statements (the new-format fallback parser in the plan), it
  needs its own confirmation step and ADR.
