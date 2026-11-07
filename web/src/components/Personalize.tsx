// The controls behind each person's own settings (ADR-026).
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { PEOPLE, useColumns, useDensity, usePerson, useSavedViews, type Person } from "../prefs";

/** Both / Hernan / Lauren, in the sidebar: Spending and Transactions follow it. */
export function PersonSwitch() {
  const [person, setPerson] = usePerson();
  return (
    <fieldset className="px-3">
      <legend className="mb-1.5 text-[11px] font-semibold tracking-widest text-nav-muted uppercase">
        Showing
      </legend>
      <div className="flex rounded-[10px] bg-nav-well p-1">
        {PEOPLE.map((p) => (
          <label
            key={p}
            className={`flex h-8 flex-1 cursor-pointer items-center justify-center rounded-lg text-xs font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary ${
              person === p
                ? "bg-ground font-semibold text-ink shadow-sm"
                : "text-nav-ink hover:text-nav-strong"
            }`}
          >
            <input
              type="radio"
              name="person"
              value={p}
              className="sr-only"
              checked={person === p}
              onChange={() => setPerson(p)}
            />
            {p}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** A small note on a page that follows the switch, so a filtered page never looks complete. */
export function PersonNote({ person }: { person: Person }) {
  const [, setPerson] = usePerson();
  if (person === "Both") return null;
  return (
    <p className="mt-4 inline-flex flex-wrap items-center gap-2 rounded-full bg-info-bg px-4 py-1.5 text-sm">
      Showing {person}’s lines only.
      <button type="button" className="font-semibold underline" onClick={() => setPerson("Both")}>
        Show both
      </button>
    </p>
  );
}

/** Columns for one table, and row size for every table. */
export function TableSettings({
  table,
  columns,
  defaults,
}: {
  table: string;
  columns: Record<string, string>;
  defaults?: string[];
}) {
  const all = Object.keys(columns);
  const [shown, setShown] = useColumns(table, all, defaults);
  const [density, setDensity] = useDensity();
  return (
    <details className="relative">
      <summary className="btn btn-quiet h-10 cursor-pointer list-none px-4 text-sm">
        Columns &amp; rows
      </summary>
      <div className="absolute right-0 z-20 mt-2 w-60 space-y-4 rounded-2xl border border-line bg-ground p-4 shadow-lg">
        <fieldset>
          <legend className="label">Columns</legend>
          {all.map((c) => (
            <label key={c} className="flex items-center gap-2 py-1 text-sm">
              <input
                type="checkbox"
                checked={shown.includes(c)}
                onChange={(e) => setShown(e.target.checked ? [...shown, c] : shown.filter((x) => x !== c))}
              />
              {columns[c]}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend className="label">Rows (every table)</legend>
          {(["comfortable", "compact"] as const).map((d) => (
            <label key={d} className="flex items-center gap-2 py-1 text-sm capitalize">
              <input type="radio" name="density" checked={density === d} onChange={() => setDensity(d)} />
              {d}
            </label>
          ))}
        </fieldset>
      </div>
    </details>
  );
}

/** Save the page as it is now (filters, and who it shows) under a name in the sidebar. */
export function SaveView({ month }: { month?: string }) {
  const { pathname, search } = useLocation();
  const [person] = usePerson();
  const { add } = useSavedViews();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [keepMonth, setKeepMonth] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  if (!open)
    return (
      <span className="flex items-center gap-3">
        <button type="button" className="btn btn-quiet h-10 px-4 text-sm" onClick={() => setOpen(true)}>
          Save view
        </button>
        <span aria-live="polite" className="text-sm text-good-ink">
          {saved && `Saved “${saved}” in the sidebar.`}
        </span>
      </span>
    );
  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-ground p-3"
      aria-label="Save this view"
      onSubmit={(e) => {
        e.preventDefault();
        const label = name.trim();
        if (!label) return;
        const q = new URLSearchParams(search);
        if (!keepMonth) q.delete("month");
        const qs = q.toString();
        add({ name: label, path: pathname, search: qs ? `?${qs}` : "", person });
        setSaved(label);
        setName("");
        setOpen(false);
      }}
    >
      <label>
        <span className="label">Name</span>
        <input
          className="field w-56"
          maxLength={40}
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          placeholder={person === "Both" ? "e.g. Needs a category" : `e.g. ${person}’s month`}
        />
      </label>
      {month && (
        <label className="flex h-11 items-center gap-2 text-sm">
          <input type="checkbox" checked={keepMonth} onChange={(e) => setKeepMonth(e.target.checked)} />
          Always {month}
        </label>
      )}
      <button type="submit" className="btn btn-secondary" disabled={!name.trim()}>
        Save
      </button>
      <button type="button" className="btn btn-quiet" onClick={() => setOpen(false)}>
        Cancel
      </button>
    </form>
  );
}

/** Saved views in the sidebar: opening one also sets who it shows. */
export function SavedViewLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { views, remove } = useSavedViews();
  const [, setPerson] = usePerson();
  if (!views.length) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <div className="mx-3 mt-4 mb-1 text-[11px] font-semibold tracking-widest text-nav-muted uppercase">
        Saved views
      </div>
      {views.map((v) => (
        <div key={v.id} className="group flex items-center rounded-[10px] hover:bg-nav-well">
          <Link
            to={`${v.path}${v.search}`}
            className="flex h-10 min-w-0 flex-1 items-center px-3 text-sm font-medium text-nav-ink hover:text-nav-strong"
            onClick={() => {
              setPerson(v.person);
              onNavigate?.();
            }}
          >
            <span className="truncate">{v.name}</span>
          </Link>
          <button
            type="button"
            className="h-10 px-3 text-nav-muted hover:text-nav-strong"
            aria-label={`Remove saved view ${v.name}`}
            onClick={() => remove(v.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
