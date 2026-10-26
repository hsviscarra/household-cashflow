// Every page of the app, with the roadmap feature that fills it in.
export type PageDef = { path: string; label: string; feature: string; summary: string };

export const PAGES: PageDef[] = [
  {
    path: "/",
    label: "Overview",
    feature: "F2",
    summary: "Monthly cash flow, KPIs and the 2021 onward history.",
  },
  {
    path: "/spending",
    label: "Spending",
    feature: "F13",
    summary: "Categories, people, countries, fixed vs variable.",
  },
  {
    path: "/transactions",
    label: "Transactions",
    feature: "F4",
    summary: "Every loaded line, searchable and editable.",
  },
  {
    path: "/review",
    label: "Review",
    feature: "F9",
    summary: "Merchants no rule knows: choose a category once, with Claude's suggestion.",
  },
  {
    path: "/recurring",
    label: "Recurring",
    feature: "F11",
    summary: "Monthly templates and the month grid.",
  },
  {
    path: "/import",
    label: "Import",
    feature: "F3",
    summary: "Upload statements, review the preview, approve.",
  },
  {
    path: "/subscriptions",
    label: "Subscriptions",
    feature: "F14",
    summary: "Recurring charges and weekly app billing.",
  },
  {
    path: "/debt",
    label: "Debt & Net Worth",
    feature: "F14",
    summary: "Interest and fees per card, balances.",
  },
  {
    path: "/projections",
    label: "Projections",
    feature: "F15",
    summary: "Next three months and cash timing.",
  },
  {
    path: "/status",
    label: "Data Status",
    feature: "F12",
    summary: "Coverage per source and month completeness.",
  },
  {
    path: "/settings",
    label: "Settings",
    feature: "F1",
    summary: "Accounts, categories and merchant rules.",
  },
];
