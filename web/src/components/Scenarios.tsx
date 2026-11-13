import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchProjection,
  runScenario,
  type ForecastChange,
  type ForecastOptions,
  type Projection,
} from "../api";
import { money, monthShort, num } from "../money";
import { useSettings } from "../prefs";
import { CashLines } from "./flowcharts";

// Saved scenarios, side by side (ADR-096, plan item C3): a set of what-ifs gets a name, is kept
// for the person, and up to three are compared with the forecast as it is: cash by month, the
// lowest point, and the difference at the end.

export type SavedScenario = { name: string; changes: ForecastChange[] };
export const MAX_SAVED = 12;
export const MAX_COMPARED = 3;
const KEY = "forecast:scenarios";
const COLORS = ["var(--color-flow-out)", "#0F766E", "#C2410C"];

/** The saved scenarios, with anything that isn't one left out. */
export function savedScenarios(value: unknown): SavedScenario[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (s): s is SavedScenario =>
      typeof s === "object" && s !== null && typeof s.name === "string" && Array.isArray(s.changes),
  );
}

/** Saving under a name that exists replaces it; the newest comes first. */
export function withScenario(list: SavedScenario[], s: SavedScenario): SavedScenario[] {
  return [s, ...list.filter((x) => x.name !== s.name)].slice(0, MAX_SAVED);
}

const minus = (v: string | number) => (num(v) < 0 ? `−${money(Math.abs(num(v)))}` : money(v));
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v))}`;
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function Scenarios({
  opts,
  changes,
  setChanges,
}: {
  opts: ForecastOptions;
  changes: ForecastChange[];
  setChanges: (c: ForecastChange[]) => void;
}) {
  const { settings, set } = useSettings();
  const saved = savedScenarios(settings[KEY]);
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const compared = saved.filter((s) => picked.includes(s.name));

  // The forecast as it is; the page asks for the same one, so it is fetched once.
  const base = useQuery({
    queryKey: ["projections", opts, []],
    queryFn: () => fetchProjection(opts),
    enabled: compared.length > 0,
  });
  const runs = useQueries({
    queries: compared.map((s) => ({
      queryKey: ["projections", opts, s.changes],
      queryFn: () => runScenario(opts, s.changes),
    })),
  });
  const ready = base.data && runs.every((r) => r.data);
  const failed = base.error ?? runs.find((r) => r.error)?.error;

  const save = () => {
    const title = name.trim();
    if (!title || !changes.length) return;
    set(KEY, withScenario(saved, { name: title, changes }));
    setName("");
  };
  const toggle = (title: string) =>
    setPicked(
      picked.includes(title)
        ? picked.filter((n) => n !== title)
        : picked.length < MAX_COMPARED
          ? [...picked, title]
          : picked,
    );

  return (
    <section className="card mt-6" aria-labelledby="scenarios">
      <h2 id="scenarios" className="font-display text-xl font-bold">
        Saved scenarios
      </h2>
      <p className="mt-1 text-sm text-muted">
        Add what-ifs above, give them a name, and compare up to {MAX_COMPARED} with the forecast as it is.
      </p>
      {changes.length > 0 && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <label>
            <span className="label">
              Save {changes.length === 1 ? "this what-if" : `these ${changes.length} what-ifs`} as
            </span>
            <input
              className="field !w-64"
              maxLength={60}
              placeholder="New car"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-secondary" disabled={!name.trim()}>
            Save scenario
          </button>
        </form>
      )}
      {saved.length === 0 ? (
        <p className="mt-3 text-sm text-muted">Nothing saved yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-line text-sm" aria-label="Saved scenarios">
          {saved.map((s) => (
            <li key={s.name} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`Compare ${s.name}`}
                  checked={picked.includes(s.name)}
                  disabled={!picked.includes(s.name) && picked.length >= MAX_COMPARED}
                  onChange={() => toggle(s.name)}
                />
                <span>
                  <strong>{s.name}</strong>{" "}
                  <span className="text-muted">
                    · {s.changes.length} {s.changes.length === 1 ? "what-if" : "what-ifs"}
                  </span>
                </span>
              </label>
              <span className="flex gap-3">
                <button
                  type="button"
                  className="text-primary underline"
                  aria-label={`Load ${s.name}`}
                  onClick={() => setChanges(s.changes)}
                >
                  Load
                </button>
                <button
                  type="button"
                  className="text-primary underline"
                  aria-label={`Delete ${s.name}`}
                  onClick={() => {
                    set(
                      KEY,
                      saved.filter((x) => x.name !== s.name),
                    );
                    setPicked(picked.filter((n) => n !== s.name));
                  }}
                >
                  Delete
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {failed && (
        <p role="alert" className="mt-3 text-sm text-danger-ink">
          {(failed as Error).message}
        </p>
      )}
      {compared.length > 0 && !ready && !failed && <p className="mt-3 text-sm text-muted">Comparing…</p>}
      {compared.length > 0 && ready && (
        <Compared
          base={base.data!}
          runs={compared.map((s, i) => ({ name: s.name, p: runs[i].data!, color: COLORS[i] }))}
        />
      )}
    </section>
  );
}

function Compared({
  base,
  runs,
}: {
  base: Projection;
  runs: { name: string; p: Projection; color: string }[];
}) {
  const all = [{ name: "As it is", p: base, color: "var(--color-primary)" }, ...runs];
  const end = (p: Projection) => num(p.end_cash ?? p.months[p.months.length - 1]?.end_cash ?? 0);
  const row = (label: string, pick: (p: Projection) => string, strong = false) => (
    <tr className={strong ? "font-semibold" : ""}>
      <th scope="row" className="py-1.5 pr-3 text-left font-medium">
        {label}
      </th>
      {all.map((s) => (
        <td key={s.name} className="num px-2 py-1.5 text-right">
          {pick(s.p)}
        </td>
      ))}
    </tr>
  );
  return (
    <div className="mt-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Scenarios compared</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 text-left font-semibold">
                &nbsp;
              </th>
              {all.map((s) => (
                <th key={s.name} scope="col" className="px-2 py-1 text-right font-semibold">
                  <span
                    aria-hidden
                    className="mr-1.5 inline-block h-0.5 w-4 align-middle"
                    style={{ background: s.color }}
                  />
                  {s.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {row("Lowest cash", (p) =>
              p.lowest ? `${minus(p.lowest.balance)} on ${day(p.lowest.day)}` : "—",
            )}
            {row("First day short", (p) => (p.first_short ? day(p.first_short) : "none"))}
            {base.months.map((m, i) => (
              <tr key={m.month}>
                <th scope="row" className="py-1.5 pr-3 text-left font-medium">
                  Cash at the end of {monthShort(m.month)}
                </th>
                {all.map((s) => (
                  <td key={s.name} className="num px-2 py-1.5 text-right">
                    {s.p.months[i] ? minus(s.p.months[i].end_cash) : "—"}
                  </td>
                ))}
              </tr>
            ))}
            {row("Difference at the end", (p) => (p === base ? "—" : signed(end(p) - end(base))), true)}
          </tbody>
        </table>
      </div>
      <div className="mt-3 rounded-2xl bg-surface p-4">
        <CashLines
          title={`Cash day by day: ${all.map((s) => s.name).join(", ")}`}
          floor={num(base.floor ?? 0)}
          series={all.map((s, i) => ({
            key: s.name,
            label: s.name,
            color: s.color,
            points: s.p.daily,
            dashed: i > 0,
          }))}
        />
      </div>
    </div>
  );
}
