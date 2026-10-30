import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { fetchHealth, fetchMe } from "./api";
import { PAGES, type PageDef } from "./pages";
import BatchPage from "./pages/Batch";
import DebtPage from "./pages/Debt";
import ImportPage from "./pages/Import";
import Overview from "./pages/Overview";
import ProjectionsPage from "./pages/Projections";
import PurchasesPage from "./pages/Purchases";
import RecurringPage from "./pages/Recurring";
import ReportPage from "./pages/Report";
import ReviewPage from "./pages/Review";
import Settings from "./pages/Settings";
import SpendingPage from "./pages/Spending";
import SubscriptionsPage from "./pages/Subscriptions";
import StatusPage from "./pages/Status";
import TransactionsPage from "./pages/Transactions";

/** The free Azure SQL database pauses after an hour without use and takes up to a minute or two
 * to resume: until then it's "waking up", not down. */
export const WAKE_MS = 2 * 60 * 1000;

export function databasePill(database: "ok" | "unavailable", downForMs: number) {
  if (database === "ok") return { label: "Database connected", className: "pill-good" };
  if (downForMs < WAKE_MS) return { label: "Database waking up…", className: "pill-wait" };
  return { label: "Database unavailable", className: "pill-bad" };
}

function StatusPill() {
  const since = useRef<number | null>(null);
  const { data, isError, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    // While the database is resuming, check again every 10 seconds.
    refetchInterval: (q) => (q.state.data && q.state.data.database !== "ok" ? 10_000 : false),
  });
  if (isLoading) return <span className="pill pill-muted">Checking…</span>;
  if (isError || !data) return <span className="pill pill-bad">API unreachable</span>;
  if (data.database === "ok") since.current = null;
  else since.current ??= Date.now();
  const pill = databasePill(data.database, since.current ? Date.now() - since.current : 0);
  return (
    <span
      className={`pill ${pill.className}`}
      title={`Version ${data.version} (${data.git_sha})`}
      role="status"
    >
      {pill.label}
    </span>
  );
}

function SignedIn() {
  const { data } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  if (!data?.authenticated) return null;
  return <span className="text-sm text-muted">{data.name}</span>;
}

function Placeholder({ page }: { page: PageDef }) {
  return (
    <section className="max-w-3xl">
      <h1 className="font-display text-4xl font-bold leading-tight">{page.label}</h1>
      <p className="mt-3 text-lg text-muted">{page.summary}</p>
      <p className="mt-8 inline-block rounded-2xl bg-info-bg px-5 py-4">
        This page arrives with roadmap feature {page.feature}.
      </p>
    </section>
  );
}

const PAGE_ELEMENTS: Record<string, JSX.Element> = {
  "/": <Overview />,
  "/import": <ImportPage />,
  "/settings": <Settings />,
  "/transactions": <TransactionsPage />,
  "/review": <ReviewPage />,
  "/recurring": <RecurringPage />,
  "/status": <StatusPage />,
  "/spending": <SpendingPage />,
  "/purchases": <PurchasesPage />,
  "/subscriptions": <SubscriptionsPage />,
  "/debt": <DebtPage />,
  "/projections": <ProjectionsPage />,
  "/report": <ReportPage />,
};

export default function App() {
  return (
    <div className="min-h-screen bg-ground text-ink">
      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 pt-6 md:px-12">
        <div className="font-display text-xl font-bold">Household Cash Flow</div>
        <div className="flex items-center gap-3">
          <SignedIn />
          <StatusPill />
        </div>
      </header>
      <nav aria-label="Main" className="mx-auto mt-4 max-w-6xl px-4 md:px-12">
        <ul className="flex gap-1 overflow-x-auto rounded-full bg-surface p-1.5">
          {PAGES.map((p) => (
            <li key={p.path}>
              <NavLink
                to={p.path}
                end={p.path === "/"}
                className={({ isActive }) =>
                  `flex h-11 items-center whitespace-nowrap rounded-full px-4 ${
                    isActive ? "bg-ink font-semibold text-ground" : "text-ink hover:bg-line"
                  }`
                }
              >
                {p.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <main className="mx-auto max-w-6xl px-4 py-10 md:px-12">
        <Routes>
          {PAGES.map((p) => (
            <Route key={p.path} path={p.path} element={PAGE_ELEMENTS[p.path] ?? <Placeholder page={p} />} />
          ))}
          <Route path="/import/batches/:batchId" element={<BatchPage />} />
        </Routes>
      </main>
    </div>
  );
}
