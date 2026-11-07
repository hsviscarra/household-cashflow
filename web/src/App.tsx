import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { fetchHealth, fetchMe, fetchReview } from "./api";
import { PersonSwitch, SavedViewLinks } from "./components/Personalize";
import { GROUPS, PAGES, type PageDef } from "./pages";
import BatchPage from "./pages/Batch";
import DebtPage from "./pages/Debt";
import ImportPage from "./pages/Import";
import CashFlowPage from "./pages/CashFlow";
import Home from "./pages/Home";
import PeoplePage from "./pages/People";
import ProjectionsPage from "./pages/Projections";
import TaxesPage from "./pages/Taxes";
import PurchasesPage from "./pages/Purchases";
import BillsPage from "./pages/Bills";
import ReportPage from "./pages/Report";
import ReviewPage from "./pages/Review";
import Settings from "./pages/Settings";
import SpendingPage from "./pages/Spending";
import StatusPage from "./pages/Status";
import TransactionsPage from "./pages/Transactions";
import { useDensity } from "./prefs";

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
  if (!data?.authenticated || !data.name) return null;
  return (
    <span className="flex items-center gap-2 text-sm text-nav-ink">
      <span
        aria-hidden="true"
        className="flex h-7 w-7 items-center justify-center rounded-full bg-nav-well font-semibold text-nav-strong uppercase"
      >
        {data.name.charAt(0)}
      </span>
      {data.name}
    </span>
  );
}

/** Lines waiting for a category: the Inbox badge. */
function InboxCount() {
  const { data } = useQuery({ queryKey: ["review", "count"], queryFn: () => fetchReview() });
  const n = data?.uncategorized_lines ?? 0;
  if (!n) return null;
  return (
    <span className="num ml-auto rounded-full bg-primary px-2 text-xs font-bold text-on-primary">
      {n}
      <span className="sr-only"> waiting</span>
    </span>
  );
}

const NAV_ORDER = [
  "/",
  "/cashflow",
  "/spending",
  "/purchases",
  "/debt",
  "/review",
  "/transactions",
  "/people",
  "/recurring",
  "/projections",
  "/taxes",
  "/report",
  "/status",
  "/import",
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pages = NAV_ORDER.map((path) => PAGES.find((p) => p.path === path)!).filter(Boolean);
  return (
    <div className="flex h-full flex-col gap-1 px-3 py-5">
      <Link
        to="/"
        onClick={onNavigate}
        className="mb-3 hidden items-center gap-2.5 px-3 text-nav-strong lg:flex"
      >
        <span aria-hidden="true" className="h-7 w-7 rounded-lg bg-primary" />
        <span className="font-display text-lg font-semibold">Cashflow</span>
      </Link>
      <PersonSwitch />
      {GROUPS.filter((g) => g !== "More").map((g) => (
        <div key={g} className="flex flex-col gap-0.5">
          {g !== "Home" && (
            <div className="mx-3 mt-4 mb-1 text-[11px] font-semibold tracking-widest text-nav-muted uppercase">
              {g}
            </div>
          )}
          {pages
            .filter((p) => p.group === g)
            .map((p) => (
              <NavLink
                key={p.path}
                to={p.path}
                end={p.path === "/"}
                onClick={onNavigate}
                className={({ isActive }) =>
                  `flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-medium ${
                    isActive
                      ? "bg-nav-active font-semibold text-nav-active-ink"
                      : "text-nav-ink hover:text-nav-strong"
                  }`
                }
              >
                {p.label}
                {p.path === "/review" && <InboxCount />}
              </NavLink>
            ))}
        </div>
      ))}
      <SavedViewLinks onNavigate={onNavigate} />
      <div className="mt-auto flex flex-col gap-2 px-0 pt-6">
        <Link
          to="/import"
          onClick={onNavigate}
          className="flex h-10 items-center justify-center rounded-[10px] border border-nav-line text-sm font-semibold text-nav-strong hover:bg-nav-well"
        >
          Upload statements
        </Link>
        <NavLink
          to="/settings"
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex h-10 items-center rounded-xl px-3 text-sm font-medium ${
              isActive
                ? "bg-nav-active font-semibold text-nav-active-ink"
                : "text-nav-ink hover:text-nav-strong"
            }`
          }
        >
          Settings
        </NavLink>
        <div className="flex flex-col gap-2 px-3 pt-2">
          <SignedIn />
          <StatusPill />
        </div>
      </div>
    </div>
  );
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
  "/": <Home />,
  "/cashflow": <CashFlowPage />,
  "/import": <ImportPage />,
  "/settings": <Settings />,
  "/transactions": <TransactionsPage />,
  "/review": <ReviewPage />,
  "/people": <PeoplePage />,
  "/recurring": <BillsPage />,
  "/status": <StatusPage />,
  "/spending": <SpendingPage />,
  "/purchases": <PurchasesPage />,
  "/subscriptions": <BillsPage start="found" />,
  "/debt": <DebtPage />,
  "/projections": <ProjectionsPage />,
  "/taxes": <TaxesPage />,
  "/report": <ReportPage />,
};

export default function App() {
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setMenu(false), [pathname]);
  // Row size is one choice for every table (ADR-026); index.css reads it from <html>.
  const [density] = useDensity();
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);
  return (
    <div className="min-h-screen bg-canvas text-ink lg:flex">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-full focus:bg-ground focus:px-4 focus:py-2"
      >
        Skip to content
      </a>
      {/* Phone and tablet: a bar with the menu button; the sidebar opens over the page. */}
      <header className="flex items-center justify-between border-b border-nav-line bg-nav px-4 py-3 lg:hidden">
        <Link to="/" className="flex items-center gap-2 text-nav-strong">
          <span aria-hidden="true" className="h-7 w-7 rounded-lg bg-primary" />
          <span className="font-display text-lg font-semibold">Cashflow</span>
        </Link>
        <button
          type="button"
          className="flex h-11 items-center gap-2 rounded-[10px] px-4 text-sm font-semibold text-nav-strong hover:bg-nav-well"
          aria-expanded={menu}
          aria-controls="sidebar"
          onClick={() => setMenu(!menu)}
        >
          {menu ? "Close" : "Menu"}
        </button>
      </header>
      <nav
        id="sidebar"
        aria-label="Main"
        className={`${menu ? "block" : "hidden"} bg-nav lg:sticky lg:top-0 lg:block lg:border-r lg:border-nav-line lg:h-screen lg:w-60 lg:shrink-0 lg:overflow-y-auto`}
      >
        <Sidebar onNavigate={() => setMenu(false)} />
      </nav>
      <main id="content" className="min-w-0 flex-1 px-4 py-8 md:px-10 lg:py-10">
        <div className="mx-auto max-w-7xl">
          <Routes>
            {PAGES.map((p) => (
              <Route key={p.path} path={p.path} element={PAGE_ELEMENTS[p.path] ?? <Placeholder page={p} />} />
            ))}
            <Route path="/import/batches/:batchId" element={<BatchPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
