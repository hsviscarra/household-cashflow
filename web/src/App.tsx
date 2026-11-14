import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { runBankSync } from "./api";
import { PAGES, type PageDef } from "./pages";
import BatchPage from "./pages/Batch";
import DebtPage from "./pages/Debt";
import ImportPage from "./pages/Import";
import CashFlowPage from "./pages/CashFlow";
import Home from "./pages/Home";
import NetWorthManagePage from "./pages/NetWorthManage";
import PeoplePage from "./pages/People";
import ProjectionsPage from "./pages/Projections";
import TaxProjectionPage from "./pages/TaxProjection";
import TaxesPage from "./pages/Taxes";
import BudgetPage from "./pages/Budget";
import ExplorePage from "./pages/Explore";
import GoalsPage from "./pages/Goals";
import NetWorthAheadPage from "./pages/NetWorthAhead";
import SavingsPage from "./pages/Savings";
import PurchasesPage from "./pages/Purchases";
import GroceriesPage from "./pages/Groceries";
import IvaPage from "./pages/Iva";
import CategoryCheckPage from "./pages/CategoryCheck";
import ClosePage from "./pages/Close";
import BillsPage from "./pages/Bills";
import ReportPage from "./pages/Report";
import ReviewPage from "./pages/Review";
import Settings from "./pages/Settings";
import SpendingPage from "./pages/Spending";
import StatusPage from "./pages/Status";
import TransfersPage from "./pages/Transfers";
import TodoPage from "./pages/Todo";
import TransactionsPage from "./pages/Transactions";
import { useDensity, useTheme } from "./prefs";
import { FamilyTabs, Sidebar } from "./components/Sidebar";

export { WAKE_MS, databasePill, FAMILIES } from "./components/Sidebar";

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
  "/transfers": <TransfersPage />,
  "/recurring": <BillsPage />,
  "/status": <StatusPage />,
  "/todo": <TodoPage />,
  "/spending": <SpendingPage />,
  "/purchases": <PurchasesPage />,
  "/groceries": <GroceriesPage />,
  "/subscriptions": <BillsPage start="found" />,
  "/debt": <DebtPage />,
  "/debt/manage": <NetWorthManagePage />,
  "/debt/ahead": <NetWorthAheadPage />,
  "/projections": <ProjectionsPage />,
  "/budget": <BudgetPage />,
  "/goals": <GoalsPage />,
  "/explore": <ExplorePage />,
  "/savings": <SavingsPage />,
  "/taxes": <TaxesPage />,
  "/taxes/income": <TaxProjectionPage />,
  "/taxes/iva": <IvaPage />,
  "/transactions/categories": <CategoryCheckPage />,
  "/report": <ReportPage />,
  "/close": <ClosePage />,
};

export default function App() {
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setMenu(false), [pathname]);
  // Row size is one choice for every table (ADR-026); index.css reads it from <html>.
  const [density] = useDensity();
  const [theme] = useTheme();
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);
  // Bank sync (ADR-044): once per app open; the server runs it only when 12 hours have passed.
  useEffect(() => {
    runBankSync(true).catch(() => undefined);
  }, []);
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
              <Route
                key={p.path}
                path={p.path}
                element={
                  <>
                    <FamilyTabs path={p.path} />
                    {PAGE_ELEMENTS[p.path] ?? <Placeholder page={p} />}
                  </>
                }
              />
            ))}
            <Route path="/import/batches/:batchId" element={<BatchPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
