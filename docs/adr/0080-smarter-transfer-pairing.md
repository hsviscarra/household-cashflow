# ADR-080: Smarter transfer pairing

Status: accepted (0.89.0, Nov 2026)

Improvement plan, item A4. Transfers paired on their own only when the two amounts were exactly
opposite within 5 days (10 between countries, ADR-007); everything else waited on Transfers to
settle (ADR-075). Two cases repeat and need no new decision each time.

**A fee on the way.** A wire can arrive smaller than it left. When a transfer has no line of the
exact opposite amount, the workbench offers lines in another account, in the other direction,
that differ by at most 1.00 inside a country or 50.00 between countries, and by no more than 5%.
The button says the difference ("15.00 bank fee"). Pairing them splits the line that left into
the transfer (the amount that arrived, paired with the other side) and the difference under
Financial Costs / Bank Fees, so the fee is counted as spending instead of disappearing inside a
transfer. A person clicks; nothing with unequal amounts is paired automatically.

**Said once.** Settling a transfer as "the other side is ..." (a place the app doesn't follow)
remembers the place for that text and amount (`core.app_setting`, `transfer-place:<hash>`). On
every later matching run, an unpaired transfer with the same text and amount that is at least 10
days old (its real other side had time to arrive) is settled the same way, with the note
"Other side: ... (as you said before)". Unlinking it asks again.

Not done: one transfer paid as two lines. Guessing which two lines add up risks pairing
unrelated movements; it stays a manual pair until real cases show a safe rule.
