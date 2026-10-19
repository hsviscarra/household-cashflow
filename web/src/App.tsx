import { useQuery } from "@tanstack/react-query";
import { NavLink, Route, Routes } from "react-router-dom";

import { fetchHealth, fetchMe } from "./api";
import { PAGES, type PageDef } from "./pages";

function StatusPill() {
  const { data, isError, isLoading } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  if (isLoading) return <span className="pill pill-muted">Checking…</span>;
  if (isError || !data) return <span className="pill pill-bad">API unreachable</span>;
  const ok = data.database === "ok";
  return (
    <span className={`pill ${ok ? "pill-good" : "pill-bad"}`} title={`v${data.version} · ${data.git_sha}`}>
      Database {ok ? "connected" : "unavailable"}
    </span>
  );
}

function SignedIn() {
  const { data } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  if (!data?.authenticated) return null;
  return <span className="text-sm text-slate-500">{data.name}</span>;
}

function Placeholder({ page }: { page: PageDef }) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">{page.label}</h1>
      <p className="mt-2 text-slate-600">{page.summary}</p>
      <p className="mt-6 text-sm text-slate-500">Built in roadmap feature {page.feature}.</p>
    </section>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 md:flex">
      <nav aria-label="Main" className="border-b border-slate-200 bg-white md:w-56 md:border-b-0 md:border-r">
        <div className="px-4 py-4 font-semibold">Household Cash Flow</div>
        <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible">
          {PAGES.map((p) => (
            <li key={p.path}>
              <NavLink
                to={p.path}
                end={p.path === "/"}
                className={({ isActive }) =>
                  `block whitespace-nowrap rounded px-3 py-2 text-sm ${isActive ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`
                }
              >
                {p.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex-1">
        <header className="flex items-center justify-end gap-3 border-b border-slate-200 bg-white px-6 py-3">
          <SignedIn />
          <StatusPill />
        </header>
        <main className="px-6 py-8">
          <Routes>
            {PAGES.map((p) => (
              <Route key={p.path} path={p.path} element={<Placeholder page={p} />} />
            ))}
          </Routes>
        </main>
      </div>
    </div>
  );
}
