# ADR-079: A rule learned from two choices by hand

Status: accepted (0.88.0, Nov 2026)

Improvement plan, the rest of item A3. ADR-042 offered a rule on To do once a merchant had been
categorized the same way twice by hand; someone still had to accept it, and only statement lines
counted. Hernan asked for less manual work and allowed the app to decide when it is sure.

When a line's category is changed by hand (`PATCH /api/transactions/{id}`) and that merchant now
has two or more lines categorized by hand, all to one category, with no rule matching them,
`rules_suggest.learn` saves the rule (contains the merchant's text, priority 15, the person when
every line shares one) and applies it to the lines still waiting. The answer carries
`learned: {rule_id, pattern, lines}` and Transactions says so with Undo, which turns the rule
off. Lines from the bank sync count like statement lines, here and in the To do suggestions.

Never learned: a description that names no one ("TRANSFERENCIA INTERNET", ADR-058's generic
words), a merchant categorized two different ways, and a merchant that already had a rule with
that text, on or off: a rule someone turned off is not saved again.
