import { type Notify, useRefresh } from "./shared";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { copyMonth, fetchExcelRows, createFromExcel } from "../../api";
import { monthLong, money } from "../../money";
import { Link } from "react-router-dom";

// ---------------------------------------------------------------- copy
export function CopyForm({ month, onDone, notify }: { month: string; onDone: () => void; notify: Notify }) {
  const refresh = useRefresh();
  const next = (m: string, n: number) => {
    const [y, mo] = m.split("-").map(Number);
    const i = y * 12 + mo - 1 + n;
    return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
  };
  const [start, setStart] = useState(next(month, 1));
  const [end, setEnd] = useState(next(month, 1));
  const copy = useMutation({
    mutationFn: () => copyMonth({ from_month: `${month}-01`, to_start: `${start}-01`, to_end: `${end}-01` }),
    onSuccess: (r) => {
      refresh();
      notify(`Copied ${monthLong(`${month}-01`)} to ${r.count} ${r.count === 1 ? "cell" : "cells"}.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-4 flex flex-wrap items-end gap-3 rounded-2xl bg-surface p-4"
      aria-label="Copy a month"
      onSubmit={(e) => {
        e.preventDefault();
        copy.mutate();
      }}
    >
      <p className="w-full">
        Copy the expected amounts (and skips) of {monthLong(`${month}-01`)} to every month from–to. Months
        with paid lines keep theirs.
      </p>
      <label>
        <span className="label">From</span>
        <input type="month" className="field w-48" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label>
        <span className="label">To</span>
        <input type="month" className="field w-48" value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <button className="btn btn-secondary" disabled={copy.isPending || !start || !end}>
        Copy to {start === end ? monthLong(`${start}-01`) : "these months"}
      </button>
      <button type="button" className="btn btn-quiet" onClick={onDone}>
        Cancel
      </button>
    </form>
  );
}

// ---------------------------------------------------------------- from the workbook
export function ExcelPicker({ year, onDone, notify }: { year: number; onDone: () => void; notify: Notify }) {
  const refresh = useRefresh();
  const rows = useQuery({ queryKey: ["recurring", "excel", year], queryFn: () => fetchExcelRows(year) });
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const chosen = picked ?? new Set((rows.data ?? []).filter((r) => r.suggested).map((r) => r.name));
  const make = useMutation({
    mutationFn: () => createFromExcel(year, [...chosen]),
    onSuccess: (r) => {
      refresh();
      notify(
        `${r.templates} templates created; ${year} filled with ${r.entries} months, ${r.linked} linked to the sheet’s lines.`,
      );
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const toggle = (name: string) => {
    const next = new Set(chosen);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setPicked(next);
  };
  return (
    <section className="mt-4 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Rows of the ${year} sheet`}>
      <h2 className="font-display text-2xl font-bold">Rows of the Cash Flow {year} sheet</h2>
      {rows.isLoading && <p className="mt-2 text-muted">Loading the sheet’s rows…</p>}
      {rows.data && !rows.data.length && (
        <p className="mt-2">
          No {year} sheet is loaded.{" "}
          <Link className="text-primary underline" to="/import">
            Load the Excel history
          </Link>{" "}
          first.
        </p>
      )}
      {rows.data && rows.data.length > 0 && (
        <>
          <p className="mt-2 text-muted">
            Rows with a value in three or more months, or a planned value, are ticked. Each becomes a
            template, and {year} is filled with the sheet’s amounts.
          </p>
          <ul className="mt-3 grid gap-1 md:grid-cols-2">
            {rows.data.map((r) => (
              <li key={r.name}>
                <label className={`flex items-center gap-2 ${r.exists ? "text-muted" : ""}`}>
                  <input
                    type="checkbox"
                    className="h-5 w-5"
                    disabled={r.exists || r.category_id == null}
                    checked={!r.exists && chosen.has(r.name)}
                    onChange={() => toggle(r.name)}
                  />
                  <span>
                    {r.name}
                    <span className="text-sm text-muted">
                      {" "}
                      · {r.months} {r.months === 1 ? "month" : "months"} ·{" "}
                      <span className="num">{money(r.latest)}</span>
                      {r.exists ? " · already a template" : ""}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <button
              className="btn btn-primary"
              disabled={make.isPending || chosen.size === 0}
              onClick={() => make.mutate()}
            >
              {make.isPending ? "Creating…" : `Create ${chosen.size} templates`}
            </button>
            <button className="btn btn-quiet" onClick={onDone}>
              Cancel
            </button>
          </div>
        </>
      )}
    </section>
  );
}
