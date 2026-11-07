# ADR-042: Smarter rules: person, merchant name and suggested rules

Status: accepted (0.58.0, Nov 2026)

## Context

Phase 3 of the improvement plan. A rule only chose a category, so lines that belong to one person
(Lauren's Netflix on a joint card) or carry an unreadable description still needed hand work after
the category was right. And a merchant categorized by hand every month never became a rule unless
someone remembered to tick "save as rule".

## Decision

- Migration 0034 adds two optional actions to `core.merchant_rule`: `set_person` (Hernan, Lauren
  or Joint, checked) and `merchant_name` (up to 100 characters). Downgrade drops both.
- When a rule matches, at staging, on lines waiting for approval and on loaded lines without a
  category, it sets the category as before and also the person (logged in `audit.change_log` for
  loaded lines) and the merchant name. Lines categorized by hand are never touched, as before.
- `GET /api/merchant-rules/suggestions`: merchants (the same key the Review list groups by)
  categorized by hand (manual or an accepted suggestion) at least twice, always to the same
  category, that no active rule matches. Most repeated first, at most 20. The person is offered
  when every line had the same one. Saving one is an ordinary `POST /api/merchant-rules`.
- Settings → Rules shows the suggestions with Save rule and Not now; Not now is kept per user in
  the setting `rule_suggestions_dismissed` (last 200 patterns).
- The rule form gains "Also set person" and "Show merchant as"; the rule list says what else a
  rule sets.

## Not done

- Splitting a fixed share (a split creates child lines and needs its own approval flow) and tags
  (there is no tags table) were in the plan for smarter rules; both are left for later and would
  need a schema change of their own.

## Consequences

- Fewer lines need a person changed by hand; the Review list shrinks faster because repeated hand
  choices turn into rules with one click.
