# ADR-002: Loading the Cash Flow workbook as history

- Status: accepted
- Date: 2026-10-20

## Context

The "Cash Flow" workbook holds the household's monthly cash flow since August 2019, one sheet per
year. Its layout drifted over the years: row labels change ("Killa Gaudaria" / "Killa Guardería"),
the first sheet spans 29 months, 2026 mixes actual months with a plan, and several TOTAL formulas
leave rows out (for example `=SUM(B13:B27)` above an `Aliquota Ofi` row in row 11), so the workbook
understates expenses by $60 to $1,260 in 33 months of 2022 to 2025.

## Decision

- **Rows are the truth.** Every numeric row is loaded; the workbook TOTALs are only compared. The
  preview lists each month where they differ with the rows the formula skips; two 2019 months have
  typed-in totals and are listed as such. (Hernan, 2026-10-20.)
- **Months:** the last English month column of a sheet is December of the sheet's year; earlier
  columns count back. "Cash Flow 2021" therefore covers August 2019 to December 2021.
- **2026:** January to June are history; July to December go to `core.budget` as a plan.
- **Side tables:** only the 2026 ones (savings and investments, debts, Johana payments, US transfer
  payments) are read. All their cells stay in `raw.excel_cell`; debts, investment positions and the
  "remaining to pay" amounts become `core.balance_snapshot` rows. The 2021 second block and the
  2025 Spanish month columns are skipped.
- **Mapping:** `api/app/services/excel_mapping.py` maps each row label (plus its group header, e.g.
  "Health Appointments") to a transaction type and category. Guessed rows carry a question shown in
  the preview. Card payments are `debt_payment` (Transfers / Card Payment) in this cash view; once
  statements itemize a month (F4 on), card payments become transfers and drop out of spending.
- **Storage:** one `core.transaction` row per sheet cell, `source = 'excel_history'`, natural key =
  hash of sheet and cell. A load replaces all earlier Excel history in one database transaction;
  raw cells of every load are kept, and `audit.load_log` records who loaded what.
- **Views:** `mart.v_monthly_cashflow` and `mart.v_category_month`, defined in
  `api/migrations/views/` so migrations and the Docker image ship them.
- **`cash_month`** is a plain column set by the loader (first day of the month), not a computed
  column, so the same models run on SQLite in unit tests.
- **Charts** are hand-drawn SVG on the Mercado tokens instead of ECharts for now: two simple
  charts did not justify the library, and SVG follows dark mode through CSS variables. ECharts
  stays the option when waterfalls and stacked charts arrive (F13 to F15).

## Consequences

- The app's totals differ from the workbook's TOTAL rows in 34 months, by design; the preview and
  the load log say why.
- The real workbook is never committed. `tests/unit/test_real_workbook.py` checks it locally when
  `REAL_WORKBOOK` points to it; CI uses a synthetic workbook with the same layout.
