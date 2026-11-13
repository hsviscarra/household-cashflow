import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PAGES } from "../pages";

// One search box for everything (ADR-093, plan item D2): Ctrl+K or ⌘K anywhere. It finds a page,
// an action, or sends what was typed to Transactions as a search (words) or an amount.

export type Hit = { label: string; hint: string; to: string };

const ACTIONS: Hit[] = [
  { label: "Upload a statement", hint: "Action", to: "/import" },
  { label: "Add a bill", hint: "Action", to: "/recurring?view=grid" },
  { label: "Close the month", hint: "Action", to: "/close" },
  { label: "Update what you own and owe", hint: "Action", to: "/debt/manage" },
  { label: "Work through To do", hint: "Action", to: "/todo" },
];
const MONTHS_SEARCHED = 12; // how far back a search from here looks in Transactions
const MAX_HITS = 8;

/** What the typed text can open: pages and actions whose words contain every word typed, then
 * the same text as a search of the last 12 months of lines (an amount when it is a number). */
export function hits(typed: string): Hit[] {
  const text = typed.trim();
  if (!text) return ACTIONS;
  const words = text.toLowerCase().split(/\s+/);
  const has = (s: string) => words.every((w) => s.toLowerCase().includes(w));
  const pages: Hit[] = PAGES.filter((p) => has(`${p.label} ${p.summary} ${p.group}`)).map((p) => ({
    label: p.label,
    hint: "Page",
    to: p.path,
  }));
  const found = [...ACTIONS.filter((a) => has(a.label)), ...pages].slice(0, MAX_HITS - 1);
  const amount = /^\d+(\.\d{1,2})?$/.test(text) ? Number(text) : null;
  const lines: Hit =
    amount !== null
      ? {
          label: `Lines of ${amount.toFixed(2)}`,
          hint: "Transactions, last 12 months",
          to: `/transactions?months=${MONTHS_SEARCHED}&min=${amount}&max=${amount}`,
        }
      : {
          label: `Lines with “${text}”`,
          hint: "Transactions, last 12 months",
          to: `/transactions?months=${MONTHS_SEARCHED}&q=${encodeURIComponent(text)}`,
        };
  return [...found, lines];
}

export default function SearchBox() {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const list = useMemo(() => hits(typed), [typed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    if (open) input.current?.focus();
    else setTyped("");
  }, [open]);
  useEffect(() => setAt(0), [typed]);

  const go = (hit: Hit | undefined) => {
    if (!hit) return;
    setOpen(false);
    navigate(hit.to);
  };

  return (
    <>
      <button
        type="button"
        className="flex h-10 w-full items-center justify-between rounded-[10px] border border-nav-line px-3 text-sm text-nav-ink hover:text-nav-strong"
        onClick={() => setOpen(true)}
      >
        Search
        <kbd className="rounded bg-nav-well px-1.5 py-0.5 text-xs">Ctrl K</kbd>
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-24"
          role="dialog"
          aria-modal="true"
          aria-label="Search"
        >
          <button
            aria-label="Close search"
            className="absolute inset-0 bg-ink/30"
            onClick={() => setOpen(false)}
          />
          <div className="relative w-full max-w-xl rounded-2xl border border-line bg-ground p-3 shadow-xl">
            <input
              ref={input}
              type="search"
              role="combobox"
              aria-expanded="true"
              aria-controls="search-hits"
              aria-activedescendant={list[at] ? `search-hit-${at}` : undefined}
              aria-label="Search pages, actions and lines"
              className="field h-12 w-full text-base"
              placeholder="A page, an action, a merchant or an amount"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setOpen(false);
                else if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setAt((i) => Math.min(i + 1, list.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setAt((i) => Math.max(i - 1, 0));
                } else if (e.key === "Enter") go(list[at]);
              }}
            />
            <ul id="search-hits" role="listbox" aria-label="Results" className="mt-2">
              {list.map((h, i) => (
                <li
                  key={`${h.to}-${h.label}`}
                  id={`search-hit-${i}`}
                  role="option"
                  aria-selected={i === at}
                  className={`flex cursor-pointer items-center justify-between gap-3 rounded-[10px] px-3 py-2 text-sm ${
                    i === at ? "bg-surface" : ""
                  }`}
                  onMouseEnter={() => setAt(i)}
                  onClick={() => go(h)}
                >
                  <span className="font-medium">{h.label}</span>
                  <span className="text-xs text-muted">{h.hint}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
