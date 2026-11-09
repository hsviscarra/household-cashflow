# ADR-057: Nelnet on Net worth, workbook duplicates paused

Status: accepted (0.70.2, Nov 2026)

## Context

Lauren's Nelnet loan (US education, on hold, no payments in 2025–2026) had a 68,190.32 balance in
the Cash Flow workbook (Cash Flow 2025, DEUDAS) but no item on Net worth. The workbook's last
values for Stock Market (13,500), Produbanco (6,000), Mastercard HV and Diners were still counted
next to Interactive Brokers and the accounts read from statements: the same money twice. Hernan
(Nov 9 2026): add Nelnet; don't count those twice.

## Decision

Migration 0041 adds the loan **Nelnet** (liability) with the workbook balance dated Dec 31 2025,
and pauses the four workbook items when they have no value other than the workbook's. Their
history stays; they can be made active again on Net worth.

## Consequences

Net worth is about 88,000 lower: Nelnet's 68,190.32 and the 19,717.69 counted twice. Nelnet's balance changes
only when a new value is entered, since it has no payments or amortization table.
