// Every page of the app, with the roadmap feature that fills it in and its sidebar group (ADR-025).
export type NavGroup = "Home" | "Analyze" | "Daily" | "Plan" | "Reports" | "More";
export type PageDef = {
  path: string;
  label: string;
  feature: string;
  summary: string;
  group: NavGroup;
  hidden?: boolean; // reachable by address, not listed in the sidebar
};

export const GROUPS: NavGroup[] = ["Home", "Analyze", "Daily", "Plan", "Reports", "More"];

export const PAGES: PageDef[] = [
  {
    path: "/",
    label: "Home",
    group: "Home",
    feature: "F2",
    summary: "What needs you, the month in numbers, what’s coming and your goals.",
  },
  {
    path: "/cashflow",
    label: "Cash flow",
    group: "Analyze",
    feature: "F2",
    summary: "Money in and out by month, where it went, and why it changed.",
  },
  {
    path: "/spending",
    label: "Spending",
    group: "Analyze",
    feature: "F13",
    summary: "Categories, people, countries, fixed vs variable.",
  },
  {
    path: "/purchases",
    label: "Purchases",
    group: "Analyze",
    feature: "F21",
    summary: "Product by product, from electronic invoices.",
  },
  {
    path: "/transactions",
    label: "Transactions",
    group: "Daily",
    feature: "F4",
    summary: "Every loaded line, searchable and editable.",
  },
  {
    path: "/review",
    label: "Inbox",
    group: "Daily",
    feature: "F9",
    summary: "Merchants no rule knows: choose a category once, with Claude's suggestion.",
  },
  {
    path: "/people",
    label: "People & transfers",
    group: "Daily",
    feature: "F24",
    summary: "Whose money a transfer was, notes before the statement, money held for others.",
  },
  {
    path: "/recurring",
    label: "Bills & subscriptions",
    group: "Plan",
    feature: "F11",
    summary: "What repeats: a calendar of the month, by group, price changes, the year grid.",
  },
  {
    path: "/import",
    label: "Import",
    group: "Reports",
    feature: "F3",
    summary: "Upload statements, review the preview, approve.",
  },
  {
    path: "/subscriptions",
    label: "Subscriptions",
    group: "Plan",
    feature: "F14",
    summary: "Recurring charges and weekly app billing.",
    // Part of Bills & subscriptions now (ADR-031): the address still works, the sidebar doesn't list it.
    hidden: true,
  },
  {
    path: "/debt",
    label: "Net worth",
    group: "Analyze",
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
    path: "/taxes",
    label: "Gastos personales",
    group: "Plan",
    feature: "P1",
    summary: "Each person's deductible expenses from the SRI invoices, the cap and the 18% rebate.",
  },
  {
    path: "/report",
    label: "Monthly report",
    group: "Reports",
    feature: "F16",
    summary: "The month in 3 to 5 findings, and exports.",
  },
  {
    path: "/status",
    label: "Data health",
    group: "Reports",
    feature: "F12",
    summary: "Coverage per source and month completeness.",
  },
  {
    path: "/settings",
    label: "Settings",
    group: "More",
    feature: "F1",
    summary: "Accounts, categories and merchant rules.",
  },
];
