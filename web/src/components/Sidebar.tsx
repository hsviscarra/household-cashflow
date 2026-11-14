import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchMe, fetchTodo } from "../api";
import { NavLink, useLocation, Link } from "react-router-dom";
import { PAGES, GROUPS } from "../pages";
import { PersonSwitch, SavedViewLinks } from "./Personalize";
import SearchBox from "./SearchBox";
import AskClaude from "./AskClaude";
import { useTheme, type Theme } from "../prefs";

/** The free Azure SQL database pauses after an hour without use and takes up to a minute or two
 * to resume: until then it's "waking up", not down. */
export const WAKE_MS = 2 * 60 * 1000;

export function databasePill(database: "ok" | "unavailable", downForMs: number) {
  if (database === "ok") return { label: "Database connected", className: "pill-good" };
  if (downForMs < WAKE_MS) return { label: "Database waking up…", className: "pill-wait" };
  return { label: "Database unavailable", className: "pill-bad" };
}

export function StatusPill() {
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

export function SignedIn() {
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
export function TodoCount() {
  const { data } = useQuery({ queryKey: ["todo"], queryFn: fetchTodo, staleTime: 5 * 60_000 });
  const n = data?.total ?? 0;
  if (!n) return null;
  return (
    <span className="num ml-auto rounded-full bg-primary px-2 text-xs font-bold text-on-primary">
      {n}
      <span className="sr-only"> waiting</span>
    </span>
  );
}

export const NAV_ORDER = [
  "/",
  "/todo",
  "/cashflow",
  "/spending",
  "/recurring",
  "/transactions",
  "/people",
  "/debt",
  "/budget",
  "/projections",
  "/taxes",
  "/report",
];

/** Pages shown as tabs of one sidebar item (ADR-060): the item is current on any of them. */
export const FAMILIES: { home: string; label: string; tabs: [string, string][] }[] = [
  {
    home: "/spending",
    label: "Spending",
    tabs: [
      ["/spending", "Categories"],
      ["/groceries", "Groceries"],
      ["/purchases", "Purchases (invoices)"],
      ["/explore", "Explore"],
    ],
  },
  {
    home: "/transactions",
    label: "Transactions",
    tabs: [
      ["/transactions", "All lines"],
      ["/transactions/categories", "By category"],
    ],
  },
  {
    home: "/people",
    label: "People & transfers",
    tabs: [
      ["/people", "People"],
      ["/transfers", "Transfers to settle"],
    ],
  },
  {
    home: "/debt",
    label: "Net worth",
    tabs: [
      ["/debt", "Overview"],
      ["/debt/manage", "Manage"],
      ["/debt/ahead", "Years ahead"],
    ],
  },
  {
    home: "/budget",
    label: "Budget & goals",
    tabs: [
      ["/budget", "Budget"],
      ["/goals", "Goals"],
      ["/savings", "Saving"],
    ],
  },
  {
    home: "/report",
    label: "Monthly report",
    tabs: [
      ["/report", "Report"],
      ["/close", "Close the month"],
    ],
  },
  {
    home: "/taxes",
    label: "Taxes",
    tabs: [
      ["/taxes", "Deductions"],
      ["/taxes/income", "Income tax"],
      ["/taxes/iva", "Monthly IVA"],
    ],
  },
];

export function familyOf(path: string) {
  return FAMILIES.find((f) => f.tabs.some(([p]) => p === path));
}

/** The tabs above a page that belongs to a family (Spending: Categories, Groceries, Purchases). */
export function FamilyTabs({ path }: { path: string }) {
  const f = familyOf(path);
  if (!f || f.tabs.length < 2) return null;
  return (
    <nav aria-label={`${f.label} pages`} className="mb-6 flex gap-1 overflow-x-auto border-b border-line">
      {f.tabs.map(([to, label]) => (
        <NavLink
          key={to}
          to={to}
          end
          className={({ isActive }) =>
            `-mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm font-semibold ${
              isActive ? "border-primary text-ink" : "border-transparent text-muted hover:text-ink"
            }`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation();
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
            .map((p) => {
              const fam = FAMILIES.find((f) => f.home === p.path);
              const inFamily = fam?.tabs.some(([t]) => t === pathname) ?? false;
              return (
                <NavLink
                  key={p.path}
                  to={p.path}
                  end={p.path === "/"}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-medium ${
                      isActive || inFamily
                        ? "bg-nav-active font-semibold text-nav-active-ink"
                        : "text-nav-ink hover:text-nav-strong"
                    }`
                  }
                >
                  {fam?.label ?? p.label}
                  {p.path === "/todo" && <TodoCount />}
                </NavLink>
              );
            })}
        </div>
      ))}
      <SavedViewLinks onNavigate={onNavigate} />
      <div className="mt-auto flex flex-col gap-2 px-0 pt-6">
        <SearchBox />
        <AskClaude />
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
        <ThemeSwitch />
        <div className="flex flex-col gap-2 px-3 pt-2">
          <SignedIn />
          <StatusPill />
        </div>
      </div>
    </div>
  );
}

/** Light, dark or as the device is (ADR-049). */
export function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const opts: [Theme, string][] = [
    ["auto", "Auto"],
    ["light", "Light"],
    ["dark", "Dark"],
  ];
  return (
    <div role="radiogroup" aria-label="Theme" className="flex rounded-xl bg-nav-well p-1 text-xs">
      {opts.map(([v, label]) => (
        <button
          key={v}
          role="radio"
          aria-checked={theme === v}
          onClick={() => setTheme(v)}
          className={`flex-1 rounded-lg py-1.5 font-semibold ${
            theme === v ? "bg-ground text-nav-strong shadow-sm" : "text-nav-muted hover:text-nav-strong"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
