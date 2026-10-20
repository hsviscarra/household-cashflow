import { useQuery } from "@tanstack/react-query";
import { NavLink, Route, Routes } from "react-router-dom";

import { fetchHealth, fetchMe } from "./api";
import { PAGES, type PageDef } from "./pages";
import ImportPage from "./pages/Import";
import Overview from "./pages/Overview";
import Settings from "./pages/Settings";

function StatusPill() {
  const { data, isError, isLoading } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  if (isLoading) return <span className="pill pill-muted">Checking…</span>;
  if (isError || !data) return <span className="pill pill-bad">API unreachable</span>;
  const ok = data.database === "ok";
  return (
    <span
      className={`pill ${ok ? "pill-good" : "pill-bad"}`}
      title={`Version ${data.version} (${data.git_sha})`}
    >
      Database {ok ? "connected" : "unavailable"}
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
        </Routes>
      </main>
    </div>
  );
}
