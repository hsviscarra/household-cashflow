# Changelog

All notable changes per roadmap feature. Versions follow `v0.<feature>.0` until the app replaces
the Excel workbook.

## [Unreleased]

## [0.82.0] — The new Home and four measures

### Added
- Home rebuilt (ADR-073): a month picker; this month so far as Money in, Spent, Set aside and
  Left over, each against the same days of the month before; your money now in each bank account
  with its date; net worth with its history and assets by class; cash flow over 12 months;
  Interactive Brokers; budget planned vs actual; goals; what's coming up; and an ⓘ on every
  number explaining what it means and how it's calculated.

### Changed
- "Kept" is now split into Spent, Set aside and Left over, so saving, investing and the house no
  longer look like losses. The yearly Cash flow uses them too.
- Months still running are compared with the same days of the month before ("vs Oct 1–11").
- Net worth uses bank sync's balance for Capital One and Bank of America when it's newer than the
  last statement.

## [0.81.0] — Where each account stands

### Added
- Data Status: **Where each account stands**, one row per account: how its data arrives (bank
  sync, email, or you upload), the day its data covers through, and whether it is up to date, on
  its way, late, on Import or waiting on you, with what to do. Claude's daily check reads it too
  (ADR-072).

### Changed
- Capital One and Bank of America: bank sync covers their days, so their PDFs are no longer asked
  for.
- Lauren's Diners opened in September 2026, so August isn't expected (migration 0048).

## [0.80.1] — An account's opening date

### Added
- Settings → Accounts: **Opened on**. Data Status expects no statements before it, so a new card
  doesn't show its earlier months as missing (ADR-071, migration 0047).

## [0.80.0] — The house installment and Lauren's payday

### Fixed
- The new house's 3,075.36 installments and the 25,678.22 down payment, printed by Produbanco as
  plain third-party transfers, were left out of the cash flow as transfers between own accounts.
  A rule by exact amount now makes them New house debt payments, and the ones loaded were moved
  (ADR-070).
- Lauren's salary paid on the 1st or 2nd counts in the month before, so September has its salary
  and October has one instead of two.

## [0.79.0] — Claude reads taxes, groceries, bills and budget

### Added
- Six read-only tools for Claude (ADR-069): `taxes` (gastos personales by person and SRI
  category, cap and rebate), `iva_return` (Form 104 for a month), `groceries_trends` and
  `groceries_products` (a year by aisle, prices, patterns; by type and brand), `bills` (paid, due
  or late this month) and `budget` (by group, with savings goals).

## [0.78.3] — Waking the database

### Fixed
- The first call after the database paused (Claude's nightly check, the first page of the day)
  timed out at login. Logins now wait up to a minute and try again while the database wakes up
  (ADR-068).

## [0.78.2] — A line given its category counts as paid

### Fixed
- Changing a line's category now matches its month's recurring items again: rent categorized by
  hand counts as the month's rent instead of staying "not paid". A line moved to another category
  is freed from the item it was linked to.

## [0.78.1] — Pacificard statements count

### Fixed
- Data status asked for Pacificard statements back to July although they were loaded: their
  period couldn't be read from the first page at upload, so the statement list now uses the period
  the parser read, and reading a statement fills it in.

## [0.78.0] — Grocery trends, and the invoice picks the category

### Added
- **Groceries → Trends** (ADR-067): 6, 12 or 24 months of supermarket spending by aisle with the
  statements' spending as a line; compare any two months by aisle, type of product or brand;
  this month against the usual; trips a month and average basket; the usual shopping day; prices
  that went up or down; new products and regulars not bought this month.
- **The invoice decides the category** (ADR-066): when an invoice is matched to the line that paid
  it, the category holding at least 60% of its products becomes the line's (a Supermaxi receipt
  that is mostly medicine goes to Pharmacy). A category you chose is never changed.

### Changed
- The Overview's six-month groceries chart is a proper chart, with a tooltip and the statements'
  spending as a line.

## [0.77.1] — A house installment stays done

### Fixed
- A transfer given a savings or debt category (a house installment, a loan) no longer comes back
  under "Who or what is it".
- "Use for future lines too" is off for bank transfer wording such as "TRANSFERENCIA CTAS TERCEROS
  BCA ENL", which says nothing about who was paid.

## [0.77.0] — Check every category

### Added
- **Transactions → By category** (ADR-065): every category of the month (or 3 or 12 months), with
  its lines; move one, or tick several and move them together. Income, savings, debt payments and
  transfers included.

### Changed
- To do explains what a bill and a rule are, what saving or refusing a suggestion does, and what
  "Statements, imports and bills" means.

### Fixed
- Data status no longer reports a balance break when the same statement was uploaded twice.
- Groceries loads every invoice's lines in one query.

## [0.76.0] — Credit and debit notes; an unfinished month isn't compared

### Added
- Monthly IVA reads **notas de crédito and débito** (ADR-064): issued ones change your sales,
  received ones your business purchases (fields 411 and 510), listed on the page and in the
  workbook. Migration 0044.

### Fixed
- Spending no longer compares the current, unfinished month with whole months ("90% less than
  October" on November 9); it says what was spent so far.

## [0.75.0] — Net worth history without the jump

### Changed
- Net worth history counts property and vehicles from their first value back (ADR-063), so it
  no longer jumps the month their values were entered.

### Added
- Claude's tools can list any month's lines by type (savings, debt payments, transfers…).

## [0.74.0] — Monthly IVA

### Added
- **Taxes → Monthly IVA** (ADR-062): the monthly IVA return from the SRI documents: your invoices
  with the retenciones clients made, invoices received as business (IVA credit) or personal, and
  the Form 104 figures, with credit carried month to month; download the accountant's workbook.
  The SRI list import now reads your issued invoices and retenciones too. Migration 0043.

## [0.73.0] — Grocery products by type and brand

### Added
- **Groceries → Products** (ADR-061): every supermarket product of the month, 3 or 12 months,
  with where the money goes by aisle, type of product or brand, search, and each product's
  quantity, unit price and spending. Claude labels new products (aisle, type, brand) on its own;
  correct any product once and it sticks for every purchase. Migration 0042.

## [0.72.1] — Fewer menu items

### Changed
- The sidebar has 12 links instead of 16 (ADR-060): Groceries and Purchases are tabs of
  **Spending**, Budget and Goals one **Budget & goals** item, Tax deductions is **Taxes**, and
  Import is the Upload statements button at the bottom. Old addresses still work.

## [0.72.0] — Groceries

### Added
- **Groceries** (Money → Groceries, ADR-059): a month's grocery spending next to what the
  supermarket invoices say it bought: against the usual month, per week, by aisle, top products
  with their price change, stores, the last six months, and the grocery charges whose invoice
  hasn't arrived. Spending's Groceries group links to it.

## [0.71.0] — To do, one list at a time

### Changed
- **To do** (ADR-058) shows one list at a time, picked on the left, each with a plain-words "what
  to do" box; a finished task leaves the list and a message confirms it at the bottom.
- Transfers missing the other side: only months whose statements count, newest first; "Other
  side isn't in the app" settles a line whose other account the app doesn't follow, and choosing a
  transfer category settles it too (it used to stay in the list).
- "+ New person…" when saying who a transfer is; no rule from general texts like TRANSFERENCIA
  INTERNET.
- Out-of-date values: enter today's value or stop counting it, right there. Suggestions: save, a
  different category, or No (remembered). Tax deduction invoices say what they need.

## [0.70.2] — Nelnet, and no money counted twice

### Changed
- Net worth has Lauren's **Nelnet** loan (68,190.32, from the workbook; on hold) and no longer
  counts the workbook's old Stock Market, Produbanco, Mastercard HV and Diners values next to the
  real accounts (ADR-057). Migration 0041.

## [0.70.1] — Lauren's Diners statements

### Fixed
- A Diners statement goes to the main cardholder's card: it never falls back to someone else's
  account (Lauren's went to Hernan's card while hers was inactive). Reading a statement again
  re-checks an account the app chose; one picked by hand stays.
- "Compras con meses de gracia por facturar" (purchases billed in later months) is no longer read
  as this month's purchases, so those statements tie out.

## [0.70.0] — The new house on Net worth

### Added
- **New house** on Net worth (ADR-056): a purchase in progress with its 30% down payment
  (reserva, entrada and 18 installments of 3,075.36) and what's been paid so far. New
  installments add to it as they're loaded.
- **Housing / New house** (debt): the developer's trust payments are debt payments, by a rule.
  Migration 0040.

### Changed
- Giving a loan or a purchase a savings or spending category makes it a debt category.

## [0.69.0] — Money between the US and Ecuador through people

### Added
- **Transfers / Exchange through people** (ADR-055): paying someone in the US who deposits the same
  in Ecuador is no longer spending and income. Give the person that category (People & transfers)
  or pick it on the Zelle line with Always; the Zelle payment and the deposit pair up even when
  the deposit comes up to 10 days later. Migration 0039.

## [0.68.1] — Cash flow explains itself

### Changed
- Clicking a month in Cash flow's **Money in and out** chart opens every line that month counts.
- The Spending and Cash views say what question each answers.
- **Where the numbers come from** (which months count the workbook and which the statements) is on
  Cash flow, not only on Data status; the lines panel says when a month's amount is the
  workbook's.
- In To do, **Transfers missing the other side** can be given a category (a house or loan payment)
  or a person, like the Who list.

## [0.68.0] — Loan and house payments are debt payments

### Fixed
- Payments on the new house, the BIESS mortgage and Lauren's US education loans count as **debt
  payments** instead of savings or spending (ADR-054): a new category kind "Debt payments", set on
  Loan Payments, Mortgage BIESS and the categories loans and purchases are paid through; their
  lines and recurring items follow. Migration 0038.

## [0.67.0] — Confirm loan payments

### Added
- **Loan payments to confirm** in To do (ADR-053): from the amortization table loaded once, the app
  asks at month end whether the installment was paid; **Yes, paid** updates the loan's balance. No
  new table each month.
- `POST /api/holdings/{id}/installments/{number}/paid`.

## [0.66.0] — A sidebar by question, and a simpler Bills page

### Changed
- Sidebar groups (ADR-052): **Money** (Cash flow, Spending, Bills & subscriptions, Purchases,
  Transactions, People & transfers), **Wealth** (Net worth), **Plan** (Budget, Goals, Forecast),
  **Taxes & reports** (Tax deductions, Monthly report, Import).
- **Bills & subscriptions** opens on This month: one list by Late, Still to pay, Paid, with price
  changes inline; Calendar, By group, Edit (year grid) and Subscriptions are the other views.

## [0.65.0] — Where's the money

### Added
- **Where's the money?** on Cash flow (ADR-051): what you kept this year against how your bank and
  card balances changed, the gap, and what usually explains it (missing balances or statements,
  transfers with one side loaded, money with people, income that came by transfer, lines without a
  category), each linking to where it's fixed; the accounts on demand.
- `GET /api/reconcile?from=&to=`.

## [0.64.0] — Purchases use the app's categories

### Changed
- **Purchases** asks for the app's own categories (the same list as everywhere, and you can add
  one, e.g. School fees) instead of grocery groups; a product keeps its category on every invoice,
  now and later (ADR-050). Migration 0037.

### Added
- **Split the bank line by category**: an invoice whose items fall in several categories splits
  the card or bank line that paid it, so the cash flow counts each category.

## [0.63.2] — Home numbers open their lines

### Changed
- On Home, **Money in** and **Money out** and each bar of **Where it went** open the lines panel
  (ADR-048) instead of another page.

## [0.63.0] — See and fix the lines behind a number

### Added
- **Lines panel** (ADR-048): click any amount in Cash flow's yearly table (or "Fix or find lines"
  in Spending) to see every line behind it: date, account, person, who with, the statement link.
  Change a category in place, optionally as a rule, and search for lines missing from it ("Move
  here").
- `GET /api/cashflow/search`; `/api/cashflow/lines` filters by type and returns more about each line.

## [0.62.0] — To do

### Added
- **To do** (ADR-047): one list of everything that needs you (lines to categorize, transfers
  that don't say who, statements and imports, transfers missing their other side, out-of-date
  values, suggested rules and bills, tax invoices), with the action right there: a category with
  Always, a person or a category for a transfer, Pause it, Save rule, Add to bills. The sidebar
  shows its count; Inbox and Data status are inside it now.
- `GET /api/todo`.

### Changed
- A transfer given an income or expense category (Salary from your employer) no longer asks who.
- Home's "Needs you" shows To do's sections.

## [0.61.3] — Database keeps running

### Changed
- Azure SQL keeps running past the free monthly allowance (billed), capped at 1 vCore; the
  budget alert is $10 with a forecast alert (ADR-046).

## [0.61.2] — Bank sync polish

### Fixed
- Sync now runs right away after linking an account the last sync skipped, instead of waiting
  half an hour.
- Each sync asks SimpleFIN for 44 days, inside its recommended 45, so the range warning is gone.
- The Bank sync table headers sit on one row.

## [0.61.1] — Bank sync page on SQL Server

### Fixed
- Settings → Bank sync failed with 500 on Azure SQL ("Connection is busy with results for another
  command"): the accounts list was still open when the next query ran. It is read in full first.

## [0.61.0] — Tax deductions in English, with the app's categories

### Changed
- "Gastos personales" is now **Tax deductions**, in English throughout (ADR-045): SRI groups,
  dependents, VAT, supplier, and the annex CSV headers.
- Invoices take a category from the **same category list as the rest of the app**; the SRI group
  it deducts as follows from it. Migration 0036 (`invoice.category_id`).

### Fixed
- Settings → Bank sync says what went wrong, with Try again, instead of loading forever.

## [0.60.1] — Deploys always start a fresh revision

### Fixed
- The deploy workflow names each revision after its run, so a redeploy (or a rollback to the
  same image) always starts new replicas that pull the image with the current registry
  credentials, instead of leaving a failed revision in place.

## [0.60.0] — Bank sync

### Added
- **Bank sync through SimpleFIN** (ADR-044): Bank of America and Capital One movements arrive by
  themselves when the app opens (twice a day at most) as pending lines, categorized by the rules.
  When the month's statement is approved its lines take their place and keep what you set by hand.
- Settings → **Bank sync**: the accounts SimpleFIN reaches, which app account each feeds, Sync now.
- `GET /api/bank-sync`, `POST /api/bank-sync/run`, `PUT /api/bank-sync/link`; migration 0035
  (`account.sync_id`, transaction source `bank_sync`).

## [0.59.1] — Bank sync setup

### Added
- `infra/azure/setup-simplefin.sh` (ADR-044): claims the SimpleFIN setup token once and keeps the
  access URL only as a Container App secret; bootstrap and Bicep carry it through redeploys.

## [0.59.0] — Bills found in the statements

### Added
- **Found in your statements** on the Recurring and Bills pages (ADR-043): charges that repeat
  monthly, every three months or yearly with a similar amount and that no recurring item covers
  yet, with the amount, category, account, usual day and a match pattern. Add makes it a recurring
  item in one click; Not now hides it.
- `GET /api/recurring/found`.

## [0.58.0] — Smarter rules

### Added
- **Rules also set the person and the merchant name** (ADR-042): optional "Also set person" and
  "Show merchant as" on a rule, applied at staging, to waiting statements and to loaded lines
  without a category.
- **Suggested rules** in Settings → Rules: a merchant you categorized the same way at least twice
  by hand, with no rule yet, is offered as a rule with Save rule or Not now.
- `GET /api/merchant-rules/suggestions`; migration 0034: `merchant_rule.set_person` and
  `merchant_name`.

## [0.57.0] — Bills that don't come every month

### Added
- **Budget page: bills that don't come every month** (ADR-041): insurance, matrícula and other
  bills that repeat every 2 to 12 months, as an amount to set aside each month, when each is next
  due and how much should already be put aside.
- `GET /api/budget/{YYYY-MM}/yearly-bills`.

## [0.56.0] — Saving goals

### Added
- **Goals** page (ADR-040): what you're saving for, a target and optional date, where the money is
  (a bank account or a Net worth item, or an amount typed by hand) and a planned monthly amount.
  Each goal shows saved of target, a status (reached, on pace, behind, date passed, no date) and
  what it needs a month to arrive on time.
- Home's Goals widget lists active goals with their pace.
- Migration 0033: `core.goal`.

## [0.55.0] — Budget per group

### Added
- **Budget** page (ADR-039): a monthly amount per spending group from a month on, what's spent
  and left, a pace mark for today, and status (over, ahead of pace, on track). Optional rollover
  carries what's left, or overspent, into the next month.
- Start every group from its 3-month average, rounded up to $10, in one click.
- Migration 0032: `core.budget_plan`.

## [0.54.0] — The weekly digest

### Added
- **Weekly digest by email** (ADR-038): every Monday the Gmail script emails what needs you:
  lines to categorize, bills due this week or late, cash running short, unusual charges, last
  month's missing statements and invoices to sort out for gastos personales, with links into the
  app and the month's spending so far against last month.
- `GET /api/inbox` (inbox token) returns the digest as JSON, text and HTML.

### Changed
- CLAUDE.md: Claude merges a PR once every CI check passes (Hernan's call, Nov 2026).

## [0.53.0] — Invoices from the SRI's list

### Added
- **Upload the SRI list** on Purchases (ADR-037): the month's "Comprobantes electrónicos
  recibidos" from SRI en línea, uploaded or pasted. The app finds every access key, skips what it
  already has and other documents, and gets each new invoice's XML from the SRI's public
  authorization service, ten at a time. No SRI password is used or stored.
- `POST /api/invoices/sri/keys` and `POST /api/invoices/sri/fetch`; setting
  `SRI_AUTHORIZATION_URL`.

## [0.52.0] — Gastos personales

### Added
- **Gastos personales** page (ADR-036): each person's deductible invoices for the tax year in
  SRI's six categories, against the cap their cargas familiares allow, and the 18% rebate so far.
- Invoices are assigned to Hernan or Lauren from the buyer's ID while they're read
  (`INVOICE_BUYERS` secret, `infra/azure/setup-buyers.sh`); only the name is stored.
- Categories guessed from the paying line or the products; choose or fix one per invoice or for
  every invoice from an issuer; mark one not deductible.
- "Numbers for the annex (CSV)" per person: RUC, provider, category, invoices, base and total.
- Migration 0031: `core.invoice.person`, `core.invoice.gp_category`, `core.gp_issuer_rule`,
  `core.gp_profile`.

## [0.51.0] — The Clear look

### Changed
- **New look** (ADR-035): a white page and a light sidebar, near-black text with darker secondary
  text for contrast, one green accent, Plus Jakarta Sans everywhere, 10 px corners on buttons and
  fields. Money out is blue in charts. Dark mode re-tuned to match. Layout and pages unchanged.

## [0.50.0] — What a line was, and deleting a category

### Added
- **Inbox context** (ADR-034): the full date and posting date on each line, **Open the statement,
  page N**, and **More details**: the card, reference, statement period, the statement's text
  around the line (long numbers cut to the last four), the transfer email's sender and note, and
  how the same merchant was categorized before. Also on a statement waiting for approval.
- **Delete a category** in Settings: unused ones go at once; used ones move their lines, rules,
  bills and budgets to a category you choose first, with each line's change in its history.
  `GET /api/categories/{id}/uses`, `DELETE /api/categories/{id}?move_to=`.

### Changed
- The Inbox explains that saving with "Use for this merchant from now on" categorizes the
  merchant automatically in the next statements.

## [0.49.0] — Forecast and the month in ten answers

### Added
- **Forecast per account** (ADR-033): each bank account's balance day by day with its own bills
  and income, a floor to warn under, and a heads-up saying how much to move and by when.
- Horizon of 1, 3 or 12 months and everyday spending averaged over 3, 6 or 12 months, saved per
  person; money held for other people left out of the starting cash unless you count it.
- **What if**: move money between accounts each month, add something each month or a one-off,
  and see the lowest cash, first short day and end cash against the forecast without it
  (`POST /api/projections/scenario`).
- **How it's calculated** on the Forecast page, with each assumption editable in place.
- **The month in ten answers** on the Report page (`GET /api/reports/{month}/answers`), live,
  each with a link to the page behind it.

### Changed
- The day-by-day chart shows the total and each account as lines, with the floor dashed.

## [0.48.0] — Net worth you can trust at a glance

### Added
- **Freshness** on every balance (ADR-032), and **Update values (N out of date)** to see only
  the old ones.
- **Possible duplicates**: old workbook values next to a live account of the same kind, with
  Pause it.
- **Tiles**: debt payments a month and interest left on loans, with what you own by kind and
  the largest debt's share.
- **What if** on a loan: how much sooner it ends and the interest saved paying more a month.

### Changed
- Own and owe side by side on wide screens; "Coming at delivery" under what you owe.

## [0.47.0] — Bills & subscriptions, one page, any schedule

### Added
- **Any schedule** (ADR-031): monthly, every 2, 3, 4 or 6 months, yearly or once, an optional
  day of the month and a last month for installments (migration 0030).
- **Bills & subscriptions page**: a calendar of the month (paid, due, late), items by group with
  totals, price changes, the year grid and the subscriptions found in statements, with tiles
  for committed, paid so far, late and subscriptions per year.
- **Add a bill** asks how often, on which day and until when.

### Changed
- Bills and Subscriptions are one entry in the sidebar; `/subscriptions` still opens.

## [0.46.0] — Transactions you can slice, save and export

### Added
- **Transactions filters** (ADR-030): period (this month, 3 or 12 months), account, category,
  amount range, has a note, and search that also finds amounts.
- **Saved views as tabs** on Transactions; opening one also sets who it shows.
- **Columns**: a note / person column, plus merchant, posted date and country to add.
- **Export the lines shown** as CSV, and a footer with the total shown.
- **People link to their lines**: "In Transactions (12 months)" on each person, and a person
  chip on each line.

## [0.45.0] — The Inbox does more of the work

### Added
- **Autopilot** (ADR-029): after a statement is approved on its own, Claude's suggestions at 90%
  or more are accepted with a rule. The Inbox lists what it did in the last 30 days, with
  **Undo**. `AUTO_ACCEPT_CONFIDENCE` sets the bar (0 turns it off).
- **Many at once**: select merchants and accept their suggestions or give them one category.
- **Keyboard**: j/k to move, a to accept, c to choose a category, x to select, ? for help.
- **Who was it for?**: transfers that only say "TRANSFERENCIA" or "ZELLE" get a person with one
  choice.

## [0.44.0] — Spending: blocks, merchants, products and ways to save

### Added
- **Spending views** (ADR-028): Groups as blocks sized by amount (click one to see its
  merchants), Merchants (visits, spent, average ticket, invoices), Products from the invoices
  (unit price against three months before, a cheaper store and what it would have saved), and
  Fixed vs variable.
- **Spending tiles**: spent, fixed, variable and not yet explained (lines without a category).
- **Ways to save**, read from the month's lines: bank fees and interest, delivery apps, small
  frequent charges, new merchants, groups above their usual, and products cheaper elsewhere.
- Purchases links to the product prices.

### Changed
- The Top merchants list became the Merchants view.

## [0.43.0] — Home and Cash flow

### Added
- **Cash flow page** (ADR-027): money in and out for twelve months; pick a month to see where
  its money came from and went (a Sankey) and why it differs from the month before (a
  waterfall and a table of the biggest changes). Click any band or row to go from group to
  category, merchant and lines; the path above goes back up, and the view can be saved. The
  year-by-year history moved here.
- **A new Home**: what needs you, the month in numbers (with net worth and the lowest cash
  ahead), where it went, bills due in the next 14 days, goals like the new house and money held
  for others, and the Inbox. "Customize" hides and orders the widgets for each of you.
- Cash flow and Home follow the Both / Hernan / Lauren switch.

## [0.42.0] — Your own settings, the person switch and saved views

### Added
- **Both / Hernan / Lauren** (ADR-026): a switch at the top of the sidebar. Spending and
  Transactions show only that person's lines, with a note and a "Show both" link; the choice is
  remembered for each of you, on every device.
- **Columns and rows**: choose the columns of the Transactions table, and comfortable or compact
  rows for every table.
- **Saved views**: "Save view" on Transactions and Spending keeps the filters and who it shows
  under a name in the sidebar; opening it brings both back.
- **Transactions search** on the description, merchant, note or category, and a "Needs a
  category" filter.

## [0.41.0] — A new look and a sidebar

### Changed
- **Navigation** (ADR-025): a left sidebar with the pages in groups (Analyze, Daily, Plan,
  Reports) replaces the top bar; a menu button opens it on phones. The Inbox shows how many lines
  wait. Upload statements, Settings, who's signed in and the database status sit at the bottom.
- **Clearer names**: Review is now Inbox, Recurring Bills, Projections Forecast, Debt & Net Worth
  Net worth, Data Status Data health, Report Monthly report, Overview Home. Links are unchanged.
- **The Ledger look** (docs/design-system.md): Space Grotesk and Inter, a grey canvas with white
  cards, new colors in light and dark mode, KPI tiles on Home.

## [0.40.0] — The import preview shows your notes

### Added
- **Import preview:** a line a transfer note will name shows "Your note · Rubén · pago obra"; a
  line whose description has a person's text shows the person; a shared payment shows the split
  (their share, the rest yours). The note's or person's category is on the line already, so the
  preview's totals by category include it.

## [0.39.0] — Statements that tie out approve themselves

### Added
- **Automatic approval** (ADR-024): a statement whose lines add up to its totals, whose opening
  balance matches the previous statement's closing balance and that has no unreadable lines is
  approved as soon as it's read: from the Gmail script, after an upload (uploads are now read
  right away) and after Read. Anything else waits on the Import page with the reason.
- **Approve all that tie out** on the Import page: the waiting backlog in one click, oldest first,
  listing what still needs you.
- `AUTO_APPROVE=false` turns it off.
## [0.38.1] — Transfer notices past the sign-in

### Fixed
- `/api/inbox/transfer` answered 401: Container Apps sign-in matches excluded paths exactly, so
  the transfer path is now listed next to `/api/inbox` (Bicep and both setup scripts).

## [0.38.0] — Transfer notes from the banks' emails

### Added
- **The Gmail script sends the banks' transfer notices** (Produbanco sent, received and credited;
  Pichincha sent and received) to `/api/inbox/transfer`. Each becomes a transfer note with the
  other party's name and the description typed at the bank, so the statement's anonymous
  "TRANSFERENCIA" line is named and, for a known person, categorized when it's read.
- Notices for someone else's account and transfers between the household's own accounts are
  skipped; the same notice twice makes one note (the bank's reference).

## [0.37.0] — People and transfer notes

### Added
- **People & Transfers page:** tell the app about a transfer (sent or received, amount, date, for
  whom, account, category, what it was for). When the statement is read, the anonymous
  "TRANSFERENCIA" line with the same amount, within 5 days, gets the name, the category and the
  description. Notes typed after the statement match at once.
- **People:** a name, texts to find in statements ("RUBEN MIRANDA; NAPOLES") and a category; their
  lines are named and categorized automatically, and listed on their card with totals received
  and paid.
- **Money held for someone** on Debt & Net Worth: "Holding for Rubén" starts from an amount you
  enter and moves with his lines (received for him raises it, paid out for him lowers it).
- **Data Status** lists transfer notes whose statement is loaded but which found no line.
- **Shared payments:** a note can say the person's share ("Rubén's share: $852" of a $1,065
  Lopes payment). The matched line is split: their share in their category (Held for Others,
  counted in their balance), the rest in the note's category (Consulting & Freelance).
- A line's person can be set or cleared through the API (`counterparty_id`).

### Changed
- Lines that belong to a person, or that are held for others or lent, are never paired as a
  transfer between own accounts.

## [0.36.0] — A fuller category tree

### Added
- **New groups:** Insurance (health, dad's health, car, home, life), Entertainment & Leisure
  (sports and clubs, gym and fitness, outings, hobbies), Education & Career, Personal Care, Gifts &
  Celebrations, Family Support and Taxes, each with descriptions for the picker and Claude.
- **New subcategories:** Travel & Vacations (Lodging, Flights, Trip Transport, Trip Activities &
  Food), Health (Hospital, Dental), Transport (Car Maintenance, Tolls), Pets (Vet, Food &
  Supplies), Shopping (Home & Furniture), Other Income (Consulting & Freelance, Gifts Received,
  Reimbursements from Others), Transfers (Held for Others, Loans to Others, Loan Repaid to Me).
- **Rules** for merchants seen since July: Quito Tenis y Golf, Workout, Fitbod, Zurich, AIG Pay
  Club, Hospital de los Valles, Lab Ecuamerican, Kryterion, lodges and hotels, Airbnb, Kywi.

### Changed
- Travel is now **Travel & Vacations**; health insurance and dad's insurance moved to the
  Insurance group with their lines; the FlexJobs rule goes to Education & Career / Job Search.
- **Money held for others or lent** is no longer listed as a transfer "missing the other side".

## [0.35.0] — Data Status for Claude

### Added
- **`data_status` MCP tool:** Claude reads what Data Status shows (missing statements with the
  file to download, imports waiting, lines needing a category, unmatched transfers, unpaid
  recurring items) through the read-only login. It feeds a monthly reminder of the statements to
  upload. No new database grants: the load history is left out.

## [0.34.0] — Which statement to download

### Added
- **Data Status names the statement to download**, not only the missing days: "Capital One
  Venture: no statement for Oct 4–31 · download the statement closing Nov 3
  (Statement_112026_4003.pdf)". Worked out from the account's cycle: each statement closes the
  day before the next one starts, a month apart; only statements already issued are listed.
- **Statement periods:** each gap says "Download the statement closing Jul 3, 2026" with the file
  name, for banks that put the date in it (Capital One `Statement_MMYYYY_last4.pdf` by the month
  it closes, Bank of America `eStmt_YYYY-MM-DD.pdf`, Pacificard `ESTADOCUENTAYYYYMM.pdf`).

### Changed
- **"Already uploaded" says which statement it is**: "Already uploaded: Capital One, Sep 4, 2026 –
  Oct 3, 2026 (as Statement_102026_4003.pdf on …)", so a download of the wrong month is obvious.

## [0.33.0] — Statement periods on Data Status

### Added
- **Statement periods** on Data Status: per account, every statement in order with its exact
  dates and where it stands (Loaded, Waiting for approval, Doesn't tie out, Not read yet, each
  linking to it), the day its statements usually start, and the exact days no statement covers
  ("No statement: upload it"). Accounts with gaps open first.
- **The current cycle isn't "missing":** days after an account's last statement, before the bank
  issues the next one, show "Current cycle: the bank issues it around Nov 22", and the month's
  item says "(the bank issues it around Nov 22)". A Bank of America statement ending Oct 22
  leaves Oct 23–31 waiting for the November statement, so October can't be complete before then.
  Month-end statements (Produbanco) are due on the next month's last day.

### Changed
- The month-by-account table on Data Status is titled "Coverage by month".

## [0.32.2] — A statement linked to only some of its accounts

### Fixes
- **Bank of America statements failed with "covers account •••• 1862, which is not linked to
  it… upload again"**: these copies had been linked to the checking account only, and uploading
  the same file again is refused as a duplicate, so there was no way out. Reading a statement now
  links the bank's active account with those last four digits. When none has them, the message
  says to set them in Settings and read the statement again.

## [0.32.1] — Capital One credits; Data Status says what's on Import

### Fixes
- **Capital One April and June 2026 couldn't be read** ("Account summary line 'other_credits' not
  found"): with a credit in the month, the summary prints "Other Credits - $14.76", with a minus
  like Payments. Both forms are read now.
- **A refund on Capital One counted as a card payment:** "Payments, Credits and Adjustments" also
  lists refunds (an Amazon return), and every line there went to Transfers / Card Payment. Only a
  payment to the card (PYMT, PAYMENT, AUTOPAY) is one now; the rest is money back, categorized by
  the rules (Amazon → Shopping / Amazon, as a refund).
- **Data Status looked frozen after uploading:** only approved statements count, so a month kept
  saying "no statement". When the statement is already on the Import page it now says so: "…: on
  Import, uploaded, not read yet" or "…: on Import, waiting for approval".

## [0.32.0] — Filtering statements; closed accounts

### Added
- **Filter the Import list** by account (or "No account yet"), status (Not read yet, Waiting for
  approval, Doesn't tie out, Needs you, Loaded; each with its count) and file or bank name, with
  "Showing N of M" and Clear filters.
- **Closed or suspended on** for an account (Settings → Accounts; migration 0026 adds
  `core.account.closed_on`). Data Status stops expecting statements after that day: a month after
  it isn't checked for that account, and the month it closed is checked up to the closing day
  ("… (until it closed on Sep 15)"). Earlier statements still upload and load, unlike making the
  account inactive.

## [0.31.0] — Produbanco Visa

### Added
- **Produbanco Visa (card ending 5997)**: a new account (seed v6, migration 0025) and a reader
  for its statements ("Periodo : 07/01/2026 - 07/31/2026", lines ending in CONS. / N/D(*) / PAGO
  with a + or − sign). It ties out to TOTAL MONTO UTILIZADO, TOTAL CARGOS, TOTAL PAGOS Y
  CRÉDITOS, the summary and PAGO TOTAL. Same source as the savings statements: detection tells
  the card apart ("TARJETA No.:"), and the card's "CUENTA: … No. CC" is no longer read as an
  account number.
- **The Gmail script collects it**: `bancaenlinea@produbanco.com`, subject "Estado de Cuenta".
- A rule for Megadatos (Netlife) → Utilities / Phone/Internet.

## [0.30.0] — One merchant, two categories

### Added
- **Untick lines on a merchant card** (Review and a statement's page) to categorize only some of
  them; the others stay for another category. With only some lines chosen, "save a rule" turns
  off, since a rule would catch every line of the merchant (Rule details → amounts can still tell
  two bills apart).

### Fixes
- The category picker's color dot overlapped the chosen category's name: `.field` is plain CSS
  and outranked Tailwind's padding utilities, so the padding is now set inline (the ▾ arrow had
  the same problem).

## [0.29.0] — F23 Organizing categories in Settings

### Added
- **Find a category** in Settings → Categories, by name or by what goes in it.
- **Groups start collapsed**, with "▸ N subcategories" and Expand all / Collapse all.
- **How much each category is used:** "120 lines · 2 rules", or "Not used yet".
- **Move a subcategory to another group** (of the same kind) from its edit form; its lines and
  rules move with it.

## [0.28.0] — F23 Categorize before approving; Claude's suggestions in one click

### Added
- **Needs a category** on a statement's page: its uncategorized lines grouped by merchant, with
  the same cards as Review. Categorize before approving; a saved rule also reaches your other
  statements and loaded lines.
- **Ask Claude about one statement** from its page.
- **One click for a suggestion:** "✓ Use …" on each card saves Claude's suggestion (and the rule).
- **✓ Accept N likely suggestions** on Review and on a statement's page: every suggestion at 80%
  or more is accepted, with a rule each; the rest wait for you.
- Lines categorized on the statement's page keep "chosen" or "Claude's suggestion" as their
  source after approval.

### Migration
- 0024 adds `stg.stg_transaction.category_source`. Downgrade drops it.

## [0.27.0] — F23 Finding and creating categories

### Added
- **Category picker** on Review, Transactions (edit and split), Settings → Merchant rules and
  Recurring, in place of the long dropdown. Type to search groups, subcategories and their
  descriptions, ignoring accents ("cafe", "taxi", "alicuota"). The five most used come first;
  arrows and Enter work.
- **What goes in each category:** every category has a description, shown under the highlighted
  option and under the field once chosen. Claude drafted them from the merchants your rules
  already map; edit any of them in Settings → Categories.
- **Create a subcategory without leaving the page:** "+ Create … as a subcategory" in the picker,
  with its group preset. "No group fits? Create a group…" is one deliberate step further.
- Claude's category suggestions read the descriptions, so they follow your own definitions.
- `GET /api/categories` returns how many loaded lines and rules use each category.

### Migration
- 0023 adds `core.category.description` and fills the seeded categories' descriptions (only
  where empty). Downgrade drops the column.

## [0.26.11] — Rules reach statements waiting for approval

### Fixes
- **A rule saved while reviewing didn't reach the other statements** on the Import page: lines
  kept the category they got when the statement was read, so the same merchant had to be
  categorized again in every month. A rule saved in Review or Settings now also categorizes the
  uncategorized lines of every statement waiting for approval, and approving runs the current
  rules once more. Lines already categorized are never changed.

### Added
- **Apply rules again** on a statement's page, while lines still need a category.
- Review and Settings say how many lines a saved rule categorized, waiting ones included.

## [0.26.10] — The last Pichincha card installment

### Fixes
- **Pichincha card April 2026** printed the last installment as "DIFERIDO (FINAL)" and counted it
  as a charge, so TOTAL CONSUMOS MES was 66.15 short. It's now an installment like "(n/m)":
  a purchase with reference "FINAL", whose purchase date may be up to the longest plan (36
  months) before the cut-off.

## [0.26.9] — Pichincha card installments with the purchase date

### Fixes
- **Pichincha card June 2026** was 71.04 short on card 2829: the installment
  "05/01 … DIFERIDO (6/12) 71,04 426,24" prints the purchase's own date (January) and was
  rejected as outside the period. An installment ("DIFERIDO (n/m)") whose purchase date falls
  within its plan is now read as a purchase dated on the statement's cut-off, with "n/m" as its
  reference.

## [0.26.8] — A PacifiCard amount with an unreadable digit

### Fixes
- **PacifiCard April 2026** read the interest line as "INT €.04 +" (6.04), so the line was
  rejected and charges were 6.04 short. An amount with one or two unreadable characters now takes
  its printed subtotal's remainder, only when it is the one such line in its group and the
  remainder fits the characters that were read. The total-due check still has to agree.

## [0.26.7] — PacifiCard and older Pichincha card statements read again

### Fixes
- **PacifiCard reading timed out** on the server ("Reading the picture took too long", or 504 on
  Read lines): tesseract started one thread per core it could see (the host's) inside a container
  limited to half a CPU, and the threads throttled each other. It now runs with one thread
  (OMP_THREAD_LIMIT=1; 21.4 s -> 11.8 s locally), two re-reads at a time (OCR_WORKERS), and a
  5-minute limit per run.
- **PacifiCard period:** when "hasta" is unreadable ("2VOCT/2026"), the period ends on the
  "Fecha de corte" date, whose month may be read with an extra letter ("O0CT").
- **PacifiCard lines with "OCT /23"** (a space before the slash) were skipped; the October 2026
  statement was 0.29 short.
- **Pichincha card statements before July 2026** print "MOVIMIENTOS 44,59 70,00- 25,41 0,00"
  (plural, decimal comma) and stopped at "Summary line not found".

## [0.26.6] — Produbanco statements whose text comes out of order

### Fixes
- Some Produbanco PDFs give their lines out of order (Lauren's July and August 2026), and the
  line-by-line balance check failed although every amount and the totals were right. Lines are now
  put in the bank's order by chaining their printed balances from the opening one; a missing or
  misread line still fails the check.
- A period printed with an English month ("Del 01 Aug 2026") is recognized at upload, so the
  statement shows its period.

## [0.26.5] — Diners purchases with an IVA column

### Fixes
- A Diners purchase that prints IVA in its own column ("TARIFA CONSUMO GASOLINERA 0,20 0,03")
  was read as 0,20, the 0,03 taken for a deferred balance, so the card's subtotal was a few cents
  short and the statement didn't tie out (May and September 2026). The IVA is now part of the
  charge; an installment line's last number is still its remaining balance.

## [0.26.4] — Pichincha account statements with English month names

### Fixes
- The January 2026 Banco Pichincha account statement prints dates in English ("09-Dec",
  "05-Jan"), and every line was rejected as an unknown month. Jan, Apr, Aug and Dec are now read
  too (the other abbreviations are the same in Spanish).

## [0.26.3] — Imports with rejected lines open again

### Fixes
- An import whose statement has rejected lines (usually one that doesn't tie out) failed to open
  with HTTP 500 ("Connection is busy with results for another command"): the rejected lines were
  still being read when the statement's accounts were loaded, and SQL Server allows one open
  result per connection. The same pattern is fixed in the statements and recurring-template
  lists. An SQL Server test now opens such an import.

## [0.26.2] — One picture statement at a time

### Fixes
- Emailed PacifiCard statements alternately failed with HTTP 500: while one was read in the
  background, the next one's quick header read got no CPU and tesseract hit its 2-minute timeout,
  which wasn't handled. Picture statements are now read one at a time; while one is being read,
  the inbox answers 503 "send it again later" at once (the Gmail script retries on its next run),
  and a tesseract timeout or failure is an ordinary reading error.

## [0.26.1] — Emailed statements read in the background

### Fixes
- The inbox answers as soon as a statement is stored and reads it right after. A picture-only
  statement (PacifiCard) needs text recognition, which took longer than the 4 minutes Azure lets a
  request wait (HTTP 504), and the Gmail script then hit Google's 6-minute limit before reaching
  the other banks and the invoices. A statement that can't be read stays on the Import page, where
  Read shows why.
- The Gmail script stops starting new files after 4.5 minutes; the next run continues.

## [0.26.0] — F21 Purchases from electronic invoices

### F21 — Purchases, product by product
- New **Purchases** page: a month's electronic invoices (SRI facturas) with every product, the
  spending by product group (Meat & Fish, Dairy & Eggs, Baby, Household & Cleaning…), and each
  invoice matched to the card or bank line that paid it (ADR-021).
- Invoices come from the Gmail script, which now also sends every invoice XML from any vendor, or
  as XML uploads (SRI en línea, cfavorita.ec). Duplicates and credit notes are skipped; an invoice
  whose lines don't add up is refused.
- Products are grouped by a confirmed rule, a few keywords, or Claude's suggestion (only product
  descriptions are sent); confirming a group applies it to that product from then on.
- Migration 0022: `core.invoice`, `core.invoice_line`, `core.product_rule`; Claude's read-only
  login reads invoices, and the new MCP tool `purchases(month)` answers what was bought.
  Runbook `docs/runbooks/invoices.md`.

## [0.25.0] — F20 Statements by email

### F20 — Statements arrive by email
- A Google Apps Script in Gmail (`infra/gmail/Code.gs`) checks once a day for statement emails
  from Banco Pichincha (account and card), PacifiCard and Diners Club, and posts their PDFs to the
  app (ADR-020).
- Each file is stored like an upload and read into a batch that waits on the Import page for
  approval; a file already in the app is skipped. Emails are labeled `cashflow-imported` or
  `cashflow-check`; `backfill()` loads the backlog since a chosen date.
- New `POST /api/inbox`, protected by its own bearer token (`INBOX_TOKEN`) instead of the sign-in;
  one-time `infra/azure/setup-inbox.sh`; runbook `docs/runbooks/gmail-statements.md`.

## [0.24.0] — F22 Interactive Brokers portfolio

### F22 — The IBKR portfolio on the balance sheet
- Ask Claude "update my IBKR portfolio in the cash flow app": Claude reads your Interactive Brokers
  connector and saves the positions, cash and account value with the new `save_portfolio` tool
  (ADR-019). It's the MCP endpoint's only write (ADR-017 amended). A day whose positions plus cash
  don't tie out to the total within 2% is refused, and every save is in the load log.
- New Investments section on Debt & Net Worth: total, cash, unrealized gain, and each position's
  quantity, price, value, gain and share. After a week without a save it suggests asking Claude.
  A Flex report (XML) from Client Portal can be uploaded instead.
- The day's total is a value of the "Interactive Brokers" item, so it counts in net worth.
  Positions are kept per day (migration 0021, `core.investment_position`), and Claude's
  balance_sheet lists them. Runbook `docs/runbooks/ibkr.md`.

## [0.23.0] — Small improvements

### Improvements
- The status pill says "Database waking up…" (amber) while the free database resumes after an
  hour idle, checks again every 10 seconds, and only says "unavailable" after two minutes.
- Claude's MCP connection can also read the balance sheet (every asset and liability, net worth,
  commitments, net worth by month), the loans with their next installments, and the saved
  monthly reports. Migration 0020 gives the read-only login SELECT on the tables those are
  computed from (ADR-017 amended).

## [0.22.0] — F19 Bulk historical load (tooling)

### F19 — Statements from a chosen month, and the backlog
- "Statements count from" on Data Status (ADR-018): from that month on, bank and card statements
  count and the Cash Flow workbook stays as a reference; earlier months keep the workbook.
  Changing it never deletes anything (migration 0019: `core.app_setting`,
  `mart.v_excel_month`; the five mart views follow it).
- Workbook vs statements: for each month both cover, income and spending from each source and
  spending per group with its gap, biggest first (`GET/PUT /api/sources`).
- Banco Pichincha bank account statements are read (same source as the card): period from the
  last cut, the running balance, and credits and debits checked against the summary's totals and
  counts. An account statement only matches a bank account, never the card.
- Import page: "Read all" reads every unread statement oldest first; statements waiting for
  approval are grouped by month with "Approve N" for those that tie out; drops of more than 50
  PDFs upload in chunks.

## [0.21.0] — F18 Claude MCP server

### F18 — Claude reads the live numbers
- Read-only MCP endpoint at `/mcp` in the app (ADR-017), behind a bearer token (`MCP_TOKEN`).
  Tools: months, cash flow (spending or cash view), compare two months, spending by category,
  spending lines, top merchants, interest and fees.
- Every tool queries through `cashflow_reader`, a login that may only `SELECT` from the mart
  views (migration 0018 adds the `mart_reader` role; the app creates the login at start-up from
  `READER_PASSWORD`).
- `infra/azure/setup-mcp.sh` turns it on in Azure and prints the Claude desktop app's
  configuration; runbook `docs/runbooks/claude-mcp.md`.

## [0.20.1] — F17 fix: restore drill

### Fixes
- The restore drill now records any error in its result (shown on Data Status), not only the
  ones it expects: the jobs' console logs aren't kept, so the result is where the reason has to be.
- The drill's throwaway SQL Server always ends cleanly after the drill stops it (40-minute limit
  if it doesn't), so only the drill's own result decides whether a run failed.

## [0.20.0] — F17 Backups and operations

### F17 — Nightly backups, kept 30 days, and a monthly restore drill
- Nightly BACPAC export of the database to the private `backups` Blob container, with a manifest
  (size, SHA-256, migration, row counts, transactions' total). A lifecycle rule deletes backups
  after 30 days (ADR-016).
- Monthly restore drill: the latest backup is restored into a throwaway SQL Server inside the
  job and checked against its manifest; results are kept a year.
- Both run as Container Apps Jobs with their own managed identity, with no stored passwords:
  `infra/azure/backups.bicep` and the one-time `infra/azure/setup-backups.sh`. `deploy.yml`
  builds the backup image and keeps the jobs on the deployed code.
- Data Status shows the last backup and drill, and warns when either is overdue or the drill
  failed (`GET /api/backups`).
- Runbook: `docs/runbooks/backups.md` (set up, run now, restore production, restore locally).
- CI exports and restores a real database with sqlpackage, and runs the backup image.

## [0.19.0] — F16 Monthly report and export

### F16 — The month in 3 to 5 findings, and every view to download
- Report page (ADR-015), one month at a time:
  - income, spending, net and savings rate against last month and the 3-month average;
  - what is still open when the month is incomplete;
  - 3 to 5 findings.
- The findings are written by Claude (Claude Sonnet 5.5, `ANTHROPIC_REPORT_MODEL`) from facts the
  app computes: cash flow, group changes, subscriptions started or stopped, interest and fees,
  like-for-like net worth and loans, alerts, and the projection's lowest cash. Without an API key,
  or if Claude fails, rules write them.
- Only totals and group, category and merchant names reach Claude: no account numbers, people's
  names or statement text.
- Reports are saved per month (migration 0017, `core.monthly_report`); Regenerate replaces one.
- CSV and Excel export of monthly cash flow (both views), categories by month, spending lines,
  interest and fees, and transactions, for a month or a year. Excel files keep real numbers and
  dates.
- Links are on the Report page and on Overview, Spending and Debt.
- `GET /api/reports`, `GET /api/reports/{month}`, `POST /api/reports/{month}/generate`,
  `GET /api/exports`, `GET /api/exports/{dataset}.{csv|xlsx}`.

## [0.18.1] — Fix

### Fixes
- After a rebuild the browser could keep showing the previous version of the app (v0.18.0's
  loan table upload didn't appear until a hard refresh). The page is now always rechecked with
  the server; the build's hashed files are still kept.

## [0.18.0] — F14 Loan amortization tables

### F14 — The mortgage from the lender's table
- Upload the lender's amortization table (PDF) on a loan's card on Debt & Net Worth (ADR-014).
  Every installment is read: principal, interest, other charges, total, balance after, and paid
  or due.
- The table is checked before saving: installments run without gaps, each row adds up to its
  total, and each balance follows from the previous one. Only the numbers are kept; not the
  file, ID number, name or loan number.
- The loan's balance comes from the table, one value per paid installment.
- The card shows installments paid, the next installment, the payoff month, interest paid this
  year, and the interest and charges still to pay.
- Payments: the last 12 installments and the next 3, each with the bank line that paid it, or a
  note when no line is found.
- Projections use the table's installment for a recurring item linked to the loan, and nothing
  after payoff.
- `POST /api/holdings/{id}/schedule`, `GET /api/holdings/{id}/payments`; migration 0016 adds
  `core.loan_installment`.

## [0.17.0] — F15 Projections

### F15 — The next 3 months on screen
- Projections page (ADR-013): the next three months in cash terms, built from:
  - income and fixed outflows from the recurring items;
  - variable spending (the average of the last three months' bank spending no recurring item
    paid);
  - purchase installments.
- For each month, net and cash at month end, starting from the bank balances on the latest
  statements, and each month's items by day.
- Cash day by day up to the end of the third month: the lowest balance and the payday after it,
  with a warning when cash goes below zero, and a chart with its table.
- Alerts for spending groups more than 30% above their previous three-month average, with a
  link to Spending.
- `GET /api/projections`. No schema change.

### Fixes
- Dates entered on the balance sheet (and the Recurring page's default month) used the UTC date,
  which is already tomorrow in Quito after 7 pm; they now use the local date.

## [0.16.0] — F14 Balance sheet

### F14 — What the household owns and owes (Debt & Net Worth)
- Balance sheet (ADR-012) at the top of Debt & Net Worth: net worth, what you own, what you
  owe and what is still to pay on purchases, then cards grouped by kind (property, vehicles,
  investments, cash, purchases in progress; loans, credit cards, owed to people), and net worth
  over the last 24 months with its table.
- Bank and card balances from each latest statement. Holdings (`core.holding`, migration 0015)
  valued by dated snapshots: the workbook's debts and savings become holdings, and anything else
  is added on the page with its value and the date it was bought. Update value, history, edit,
  pause, remove.
- A purchase in progress (the new house's down payment) shows paid so far, installments left
  and the amount financed at delivery. A loan shows its monthly payment from Recurring.
- `GET /api/networth`, `POST/PATCH/DELETE /api/holdings`, values per holding.

## [0.15.0] — F14 Subscriptions and cost of debt

### F14 — Capital One YTD interest shown; Pichincha app subscriptions listed
- Subscriptions page (ADR-011): charges that repeat weekly, monthly, quarterly or yearly with a
  similar amount, found in the statements (weekly app billing included). Each shows its card,
  typical amount, monthly and yearly cost, last and next charge, and Active or Stopped?; one-off
  charges in a subscription category are listed as possible.
- Debt & Net Worth page: interest and fees per account for the year and the last 12 months, by
  kind and by month, each card's latest statement balance, and a chart with its table.
- `mart.v_debt_cost` (migration 0014). `GET /api/subscriptions`, `GET /api/debt`.

## [0.14.0] — F13 Spending analytics

### F13 — One month's spending analysis fully in the app
- Spending page (ADR-010): a headline with the month's spending against last month and the same
  month last year, then:
  - categories grouped with their colors, each with MoM and YoY, expanding to subcategories and
    the lines behind them;
  - by person, by country, and fixed vs variable, each clickable to its lines;
  - the top 10 merchants of statement months;
  - the last 12 months as a chart with a table of the same numbers.
- `mart.v_spending_line` (migration 0013): one row per spending line. The page's total equals
  the Overview's spending view for every month.
- `GET /api/spending`, `GET /api/spending/lines`.

## [0.13.0] — F12 Month status

### F12 — Each month shows complete or what is missing
- Data Status page (ADR-009): every month from the end of the Cash Flow sheet to today is
  Complete or lists what is missing, each item with a link to fix it.
  - Statements: the days no approved statement covers, per active account (card statements
    counted by day).
  - Imports waiting for approval or failing their tie-out.
  - Lines without a category, transfers without their other side.
  - Recurring items not paid yet.
  - Balance breaks between consecutive statements.
- Coverage table (accounts × months: full, part with days, none) and the load log.
- `GET /api/status`. No schema change.

### Fixes
- Recurring "Change from month X" failed on SQL Server (`is_override IS 0` is not valid T-SQL);
  it now filters with `= 0`. A unit test guards against boolean `IS` comparisons.

## [0.12.0] — F11 Recurring entries

### F11 — The 2026 workbook rows reproduced in the month grid
- Recurring page (ADR-008): rows grouped as Income and Expenses like the sheet, January to
  December, paid amounts (linked lines) or expected ones, with Money in, Money out and Left.
  Select a cell to set this month only, change from this month on, skip it, or link and unlink
  lines; select an item to edit, pause or remove its template.
- Templates with an amount history; Generate a month; Copy a month forward or to a range.
- "From the 2026 sheet" turns the workbook's rows into templates and fills the year: past months
  linked to the history lines, the rest from the sheet's plan.
- Matching to statement lines by category, account (or the transfer's other side) and description
  pattern within a tolerance; two lines can pay one item. Runs after approve and reload.
- The Overview's plan uses the recurring entries for months that have them.
- Migration 0012 (`recurring_template`, `recurring_amount`, `recurring_entry`,
  `transaction.recurring_entry_id`) with a working downgrade.

### Tests
- The e2e spec for the Review page waits for its queue before checking it (0.11.0 follow-up).

## [0.11.0] — F10 Transfers and two views

### F10 — Card payments left out of spending and shown in the cash view
- Transfer matching across accounts (ADR-007): opposite, equal amounts on two accounts within 5
  days are linked (`transfer_group_id`) and categorized *Card Payment* or *Between Own Accounts*;
  runs after approve, after resolving or editing a line into a transfer, and on demand. A category
  chosen by hand is never overridden; a wrong pair is unlinked in one click; every change logged.
- New `mart.v_monthly_cash` and `GET /api/cashflow/monthly?view=cash`: bank accounts only, card
  payments counted as cash out, moves between own accounts left out.
- Overview: Spending view / Cash view toggle. Transactions: a matched line names the other
  account and date. Review: "Transfers without their other side", with "Match transfers again".
- Migration 0011 (column, index, `category_source = 'match'`, the view) with a working downgrade.

## [0.10.3] — Claude suggestions answer with ids

- The log showed the real cause: a merchant description with double quotes (a Zelle payment
  "FOR \"… ORDER\";") came back unescaped inside Claude's JSON, so the whole answer failed. Claude
  now answers with short ids for merchants and categories ("m1", "c3"), mapped back on the server,
  so no description or category name is ever repeated inside the JSON.

## [0.10.2] — Claude suggestions, tolerant reading

- Claude's reply finished normally but wasn't in the exact expected shape, so it was rejected. The
  reply is now read even with a code fence or words around the JSON, a bare list, or
  "merchant"/"category" field names; one bad item is skipped instead of failing all; category
  names match regardless of spacing and case. An unreadable reply logs the parse error and its
  first 300 characters.

## [0.10.1] — Claude suggestions fix

- "Claude's answer could not be read": Claude Haiku 5.5 thinks before answering and that counts
  toward max_tokens, so the JSON was cut off. Suggestions now run at low effort with a 16,000-token
  limit and at most 20 merchants per request; a cut-off or declined answer is reported as such.

## [0.10.0] — F9 Classification

### F9 — Unknown merchants of a month resolved in one screen
- Review page: uncategorized lines grouped by merchant (reference numbers and confirmation codes
  ignored), biggest amounts first; choose a category once, optionally save a rule (pattern, match,
  amount range) that is applied right away to every other uncategorized line it matches.
- Claude suggestions with confidence (ADR-006): `claude-haiku-5-5`, JSON-schema answers limited to
  Hernan's categories, only description/amount/date/bank sent, nothing applied until accepted.
  `ANTHROPIC_API_KEY` passed by Compose, Bicep and the bootstrap.
- Transactions page: edit a line's category and note (with Undo), split a line across categories
  (the parts must add up; the views count the parts instead of the line), each line's history.
- Merchant rules can carry an amount range; the Produbanco IESS split (empleada IESS vs BIESS)
  is now two editable rules instead of code (seed v4). The rule tester takes an amount.
- `audit.change_log` records every edit with old and new values and who made it; lines record
  where their category came from (rule, statement section, chosen, suggestion, workbook, split).
- Migration 0010 (rule ranges, splits, category source, change log, suggestions; views skip a
  split line; downgrade refuses while splits exist). Deleting a rule keeps the categories it gave.

## [0.9.2] — OCR fallback for every bank

- A statement PDF without text (a scan) is recognized and read with OCR for any bank, then goes to
  that bank's parser and tie-out (ADR-005 update). Scans of all five text formats tie out.
- OCR adapts to the picture's resolution, keeps signs, "$" and the decimal mark of each amount, and
  rejects impossible amounts ("00,00").
- Diners matches labels without accents; Produbanco recovers a lost sign from the running balance;
  Pacificard settles a tie between two printings of a total with the one the lines balance with.

## [0.9.1] — F8b Pacificard

### F8b — Banco del Pacífico Mastercard, read from a screenshot
- Pacificard statements are pictures (a saved web page with a "COPIA" watermark): they are read
  with Tesseract OCR inside the app (ADR-005), amounts and dates re-read digits-only and decided by
  majority; the parser handles OCR noise and the tie-out blocks any misread digit. The real Apr –
  Sep 2026 statements tie out and chain month to month.
- New account "Pacificard Mastercard Black" (Lauren's additional card goes to Lauren) and rules for
  SOLCA, IVA on digital services, credit-life insurance and AWS (migration 0009, seed v3);
  `raw.statement_file` accepts the new source.
- The Import page explains the wait while a picture is read.
- `tesseract-ocr` in the Docker image and CI.

## [0.9.0] — F8 Diners Club

### F8 — Diners statements, main and additional cards
- Diners Club parser (docs/parsers.md) for Hernan's and Lauren's statements: one block per card,
  deferred purchases (installment billed on the closing date, remaining balance checked),
  interest, late and collection charges, SOLCA, payments across a page break; golden test with a
  main and an additional card; the real Jul, Aug and Oct 2026 statements tie out.
- Upload matches a Diners statement to Hernan's or Lauren's account by the main cardholder's name
  ("Matched by the cardholder's name" on the Import page); detection now reads Diners card digits
  and the period.
- Continuity compares only with an adjacent statement, so a missing month no longer blocks a
  correct statement.
- Reading an unrecognized format says so plainly.

## [0.8.0] — F7 Produbanco

### F7 — Savings accounts with a running balance
- Produbanco parser (docs/parsers.md) for Hernan's and Lauren's accounts: Spanish month names,
  signed amounts, `#` IVA marks removed; ties out opening + lines = closing and checks every
  printed running balance; golden test on a synthetic statement; the real Jun, Jul and Aug 2026
  statements tie out (Jul 297.71 → 6.73) and chain month to month.
- Fees (`TARIFA`), card payments and capitalized interest are categorized by section.
- The two IESS payments that print the same are split by amount: the empleada's IESS and the
  BIESS house loan.

## [0.7.0] — F6 Banco Pichincha

### F6 — Spanish card statement with deferred purchases
- Banco Pichincha parser (docs/parsers.md): Spanish layout, both number formats, account-level
  lines (payments, interest, SOLCA, IVA withheld on digital services, early payoffs of deferred
  purchases), one block per card (replacement 6331 and original 2829), installments of deferred
  purchases; golden test on a synthetic statement; the real Jun 13 – Jul 12, 2026 statement ties
  out to 44.59 with every line categorized.
- Lines without a cardholder take the account owner as the person.
- ADR-004 and migration 0008: a month counts from the Excel history or from statements, never
  both; statement lines in history months are kept and listed with a note.
- Review page labels installments ("installment 2 of 6") and shows references on phones.

## [0.6.0] — F5 Bank of America

### F5 — Checking and savings from one combined statement
- Bank of America parser (docs/parsers.md): two accounts per statement, wrapped descriptions,
  deposits / withdrawals / card / checks / service fees sections; golden test on a synthetic
  statement; the real Aug 22 – Sep 22, 2026 statement ties out for both accounts.
- Staging handles statements that cover several accounts: each line goes to its account, each
  account ties out and is checked for continuity against its previous statement.
- The payer's label on a deposit (e.g. "August" on the September salary) is kept as
  `pay_reference` (migration 0007 adds it to `stg.stg_transaction`); the salary counts in the
  month it lands.
- On a bank account, money in without a rule is income (on a card it stays a refund).
- Review page shows each line's account on combined statements and the payer's label.

## [0.5.0] — F4 Capital One end to end

### F4 — Read, tie out, preview and approve a Capital One statement
- Migration 0006: `raw.statement_header`, `raw.raw_line`, `stg.import_batch`,
  `stg.stg_transaction`, `rej.rejected_line`; `core.transaction` gains `statement_file_id`,
  `raw_line_id`, `import_batch_id` and `post_date`.
- Capital One parser (docs/parsers.md): summary, lines per cardholder, fees and interest, year
  from the billing cycle; golden test on a synthetic statement; the real Sep 4 – Oct 3, 2026
  statement ties out to 3,932.84 (76 lines).
- Tie-out checks per card and for the statement, plus continuity with the previous statement.
  A statement that doesn't tie out, or has unreadable lines, can't be approved.
- Staging with merchant-rule categories, person and country per line; card payments are
  transfers, interest is a financial cost, credits on purchases are refunds. Identical lines on
  one statement are kept (each gets its own key); lines already loaded are flagged and skipped.
- Approve loads the batch into `core.transaction` in one database transaction and writes
  `audit.load_log`; Discard leaves core untouched. Re-reading a preview replaces it.
- Import page: "Read lines" per statement; review page with tie-out, totals by category, lines,
  rejects, Approve import / Discard. Transactions page (read-only) with a month picker.
- Overview: plan months give way to actual months as statements arrive.

## [0.4.0] — F3 Statement upload

### F3 — Upload, detect and keep statements
- Migration 0005: `raw.statement_file` (hash, source, status, last four digits found, period,
  storage key, who and when) and `raw.statement_file_account` (a BofA combined statement covers two
  accounts).
- Upload one or many PDFs (up to 50, 25 MB each) on the Import page or `POST /api/statements`.
  Each file is hashed; the same file is never saved twice, whatever its name.
- Detection by bank fingerprint (domains and legal names only), last four digits and statement
  period for Bank of America, Capital One, Banco Pichincha, Produbanco and Diners; unknown formats
  are kept for review. Password-protected or damaged PDFs are refused with a clear message.
- Account matching: last four digits first, then the bank's only account (replacement cards,
  Lauren's Produbanco); otherwise Hernan picks the account in the list.
- Files stored in Azure Blob Storage with the app's managed identity (`STORAGE_ACCOUNT_URL`), or a
  local folder (`STATEMENTS_DIR`, a Docker volume). `GET /api/statements/{id}/file` opens the PDF.

## [0.3.0] — F2 Excel history and first dashboard

### F2 — Excel history and Overview
- Migration 0004: `raw.excel_import` / `raw.excel_cell`, `core.transaction`, `core.budget`,
  `core.balance_snapshot`, `audit.load_log`; categories Health / Dad's Insurance, Savings & Debt /
  Loan Payments, Pets, Other Expenses; views `mart.v_monthly_cashflow` and `mart.v_category_month`.
- Workbook importer (ADR-002): August 2019 to June 2026 as monthly history, July to December 2026 as
  plan, 2026 side tables as raw cells and balance snapshots; reconciliation that names the rows each
  workbook TOTAL formula leaves out.
- Import page: preview (years, rows to confirm, TOTAL differences, balances) then Load history.
  CLI: `python -m app.cli.import_excel_history`.
- Overview page: the year in one sentence, money in / out / kept tiles, monthly columns with plan,
  running total since 2019, category table; light and dark, desktop and phone.
- API: `/api/history/excel/preview|load`, `/api/cashflow/monthly|categories|plan`.

## [0.2.0] — F1 reference data

### F1 — Accounts, categories and merchant rules
- Tables `core.account`, `core.category` (two levels, kind, color, fixed flag) and
  `core.merchant_rule` (contains / starts with / regex, priority) — migration 0002.
- Seed v1 from the project instructions (8 accounts with last four digits only, the category tree,
  50 merchant rules) — migration 0003, with a working downgrade.
- Rule engine: first active rule by priority wins; case and spacing ignored; invalid regex refused.
- API: list/create/update accounts and categories; CRUD for merchant rules; `/api/merchant-rules/test`.
- Settings page (Accounts, Categories, Merchant rules tabs) with inline edits, add forms and a rule
  tester, in the Mercado style, desktop and phone.
- Playwright end-to-end tests run in CI against the Docker image and SQL Server.

## [0.1.0] — 2026-10-19

### F0 — Walking skeleton and pipeline
- FastAPI app with `/api/health` (version, git SHA, database check) and `/api/me`.
- Email allow-list middleware for Container Apps sign-in.
- Alembic baseline creating the `raw`, `stg`, `rej`, `core`, `mart` and `audit` schemas.
- React shell with navigation to every planned page and a database status pill.
- Mercado design system (docs/design-system.md): color tokens with dark mode, Bricolage Grotesque + Figtree, category colors, button and behaviour rules; shell restyled with it.
- Single Docker image (API serves the web build); Docker Compose with SQL Server 2022.
- CI (lint, types, unit and integration tests, secret scan, image build) and deploy-on-merge to
  Azure Container Apps with smoke test and manual rollback.
- Azure Bicep (Container App, Azure SQL free offer with auto-pause, Blob, budget) and bootstrap script.
- Bootstrap registers resource providers, supports a separate SQL region and trusts GitHub's
  ID-based OIDC subject. Live in Azure South Central US.
