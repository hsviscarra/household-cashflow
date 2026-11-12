# ADR-088: Income tax projected for the year

Status: accepted (0.97.0, Nov 2026). Agreed for before February in the improvement plan.

Deductions (ADR-036) already showed the rebate each person's invoices give. What was missing is
the other half: the tax that rebate comes off, what is left to pay in March, and how much to set
aside. Hernan, Nov 12 2026: he is paid from abroad with nothing withheld; Lauren is an employee
and her employer withholds. He wants three things: the tax owed, the deductions still worth
gathering, and the cash to set aside.

## Decision

- `services/tax_projection.py`, per person and year:
  `taxable = income + withheld - exempt - deductions`, `tax = SRI table(taxable)`,
  `due = tax - rebate`, `to pay = due - withheld`.
- **Income** is read from the bank lines in the person's own category under Salary, by the day
  they arrived (tax counts receipt, not the month a salary pays for, ADR-084). Months that are
  over count what arrived; this month and the rest of the year count the typical month (the
  median of the last three complete months), or what arrived if more. A month the workbook
  counts for (ADR-018) takes the workbook's row, so nothing is counted twice.
- **The table** is the SRI's for 2026 (Resolución NAC-DGERCGC25-00000043, Dec 29 2025), kept in
  the module with its source. A year without a table answers 404; a new year is one entry.
- **The rebate** is the one Deductions computes (18% of the deductible invoices inside the cap),
  never more than the tax. "Room" is what the cap still leaves, and what filling it would take
  off.
- **What a bank line can't say** is entered per person and year, and stored in
  `core.app_setting` (`tax-profile:YYYY:Person`): how the person is taxed, the year's
  withholding, exempt income (the décimos) and deductions (IESS paid on one's own, costs). An
  employee's deposits are net of IESS and withholding, so IESS is already out and the
  withholding is added back. Until entered they are zero and the page says what that means.
- **Set aside** = what is left to pay, over the months until March 15 of the next year. The
  same payment is an event in the forecast (`projections.project`), so the 12-month view shows
  the dip.
- Taxes → Income tax (`/taxes/income`); `GET /api/taxes/{year}/projection`,
  `PUT /api/taxes/{year}/projection/{person}`. No schema change.

## Consequences

- It is an estimate: other income (interest, rent, the business's invoices and their
  retenciones), the real due date by RUC digit, and advances paid are not in it. The page says
  so and points to the accountant for the return.
- The default regimes (Hernan: paid from abroad; Lauren: employee) are constants a saved profile
  overrides.
- Each January the new year's table and basket must be added; without them the page says the
  table isn't in the app yet.
