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
    path: "/taxes",
    label: "Tax deductions",
    group: "Taxes & reports",
    feature: "P1",
    summary: "Each person's deductible personal expenses from the SRI invoices, the cap and the 18% rebate.",
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
