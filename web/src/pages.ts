// Every page of the app, with the roadmap feature that fills it in and its sidebar group (ADR-025).
// Sidebar groups (ADR-052): what happened (Money), what you have (Wealth), what's ahead (Plan).
export type NavGroup = "Home" | "Money" | "Wealth" | "Plan" | "Taxes & reports" | "More";
export type PageDef = {
  path: string;
  label: string;
  feature: string;
  summary: string;
  group: NavGroup;
  hidden?: boolean; // reachable by address, not listed in the sidebar
};

export const GROUPS: NavGroup[] = ["Home", "Money", "Wealth", "Plan", "Taxes & reports", "More"];

export const PAGES: PageDef[] = [
  {
    path: "/",
    label: "Home",
    group: "Home",
    feature: "F2",
    summary: "What needs you, the month in numbers, what’s coming and your goals.",
  },
  {
    path: "/todo",
    label: "To do",
    group: "Home",
    feature: "P5",
    summary: "Everything that needs you, in one list, with the action for each right there.",
  },
  {
    path: "/cashflow",
    label: "Cash flow",
    group: "Money",
    feature: "F2",
    summary: "Money in and out by month, where it went, and why it changed.",
  },
  {
    path: "/spending",
    label: "Spending",
    group: "Money",
    feature: "F13",
    summary: "Categories, people, countries, fixed vs variable.",
  },
  {
    path: "/groceries",
    label: "Groceries",
    group: "Money",
    feature: "F21",
    summary: "What the supermarket money buys, from the Supermaxi invoices.",
  },
  {
    path: "/purchases",
    label: "Purchases",
    group: "Money",
    feature: "F21",
    summary: "Product by product, from electronic invoices.",
  },
  {
    path: "/explore",
    label: "Explore",
    group: "Money",
    feature: "F13",
    summary:
      "Build your own view of spending: a measure, rows, columns and a period; save it and pin it to Home.",
  },
  {
    path: "/transactions",
    label: "Transactions",
    group: "Money",
    feature: "F4",
    summary: "Every loaded line, searchable and editable.",
  },
  {
    path: "/transactions/categories",
    label: "By category",
    group: "Money",
    feature: "F9",
    summary: "Every category with its lines, to check them and move the wrong ones.",
    hidden: true, // a tab of Transactions (ADR-060)
  },

  {
    path: "/review",
    label: "Inbox",
    group: "Money",
    feature: "F9",
    summary: "Merchants no rule knows: choose a category once, with Claude's suggestion.",
    hidden: true, // inside To do now (ADR-047)
  },
  {
    path: "/transfers",
    label: "Transfers to settle",
    group: "Money",
    feature: "F10",
    summary: "Transfers missing their other side: pair them, say where the money went, or recategorize.",
    hidden: true, // a tab of People & transfers (ADR-075)
  },
  {
    path: "/people",
    label: "People & transfers",
    group: "Money",
    feature: "F24",
    summary: "Whose money a transfer was, notes before the statement, money held for others.",
  },
  {
    path: "/recurring",
    label: "Bills & subscriptions",
    group: "Money",
    feature: "F11",
    summary: "What repeats: a calendar of the month, by group, price changes, the year grid.",
  },
  {
    path: "/import",
    label: "Import",
    group: "Taxes & reports",
    feature: "F3",
    summary: "Upload statements, review the preview, approve.",
  },
  {
    path: "/subscriptions",
    label: "Subscriptions",
    group: "Money",
    feature: "F14",
    summary: "Recurring charges and weekly app billing.",
    // Part of Bills & subscriptions now (ADR-031): the address still works, the sidebar doesn't list it.
    hidden: true,
  },
  {
    path: "/debt",
    label: "Net worth",
    group: "Wealth",
    feature: "F14",
    summary: "Interest and fees per card, balances.",
  },
  {
    path: "/debt/manage",
    label: "Manage net worth",
    group: "Wealth",
    feature: "F14",
    summary: "Update values, add or pause items, load a loan's table.",
    hidden: true, // a tab of Net worth (ADR-090)
  },
  {
    path: "/debt/ahead",
    label: "Net worth, years ahead",
    group: "Wealth",
    feature: "F14",
    summary:
      "Net worth five to ten years ahead: loans by their tables, investments at a return range, milestones.",
    hidden: true, // a tab of Net worth (ADR-098)
  },
  {
    path: "/projections",
    label: "Forecast",
    group: "Plan",
    feature: "F15",
    summary: "Next three months and cash timing.",
  },
  {
    path: "/budget",
    label: "Budget",
    group: "Plan",
    feature: "P2",
    summary: "A monthly budget per group, its pace and rollover.",
  },
  {
    path: "/goals",
    label: "Goals",
    group: "Plan",
    feature: "P2",
    summary: "What you're saving for and what each goal needs a month.",
  },
  {
    path: "/savings",
    label: "Saving",
    group: "Plan",
    feature: "P2",
    summary: "Savings rate by month, safe to spend, what goals need, and which debt to pay first.",
  },
  {
    path: "/taxes",
    label: "Tax deductions",
    group: "Taxes & reports",
    feature: "P1",
    summary: "Each person's deductible personal expenses from the SRI invoices, the cap and the 18% rebate.",
  },
  {
    path: "/taxes/income",
    label: "Income tax",
    group: "Taxes & reports",
    feature: "P1",
    summary: "The year's income tax projected: what is owed, what would lower it, what to set aside.",
    hidden: true, // a tab of Taxes (ADR-060)
  },
  {
    path: "/taxes/iva",
    label: "Monthly IVA",
    group: "Taxes & reports",
    feature: "P1",
    summary:
      "The monthly IVA return from the SRI documents: sales, purchases with credit, retenciones, Form 104.",
    hidden: true, // a tab of Taxes (ADR-060)
  },
  {
    path: "/close",
    label: "Close the month",
    group: "Taxes & reports",
    feature: "A8",
    summary: "What is missing, unusual or decided by the app, before the month is done.",
    hidden: true, // a tab of Monthly report (ADR-087)
  },
  {
    path: "/report",
    label: "Monthly report",
    group: "Taxes & reports",
    feature: "F16",
    summary: "The month in 3 to 5 findings, and exports.",
  },
  {
    path: "/status",
    label: "Data health",
    group: "Taxes & reports",
    feature: "F12",
    summary: "Coverage per source and month completeness.",
    hidden: true, // inside To do now (ADR-047)
  },
  {
    path: "/settings",
    label: "Settings",
    group: "More",
    feature: "F1",
    summary: "Accounts, categories and merchant rules.",
  },
];
