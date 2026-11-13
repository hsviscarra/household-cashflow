import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  fetchSpendLines,
  fetchSpending,
  type SpendCompare,
  type SpendFilter,
  type Spending,
  type SpendSlice,
} from "../api";
import SpendingChart from "../components/SpendingChart";
import { localToday, money, monthLong, monthShort, num, parts } from "../money";
import { ExportLinks } from "../components/ExportLinks";
import LinesPanel from "../components/LinesPanel";
import KpiCard from "../components/KpiCard";
import { PersonNote, SaveView } from "../components/Personalize";
import { personParam, usePerson } from "../prefs";
import { GroupMap, Ideas, MerchantTable, ProductTable, VIEWS, ViewSwitch, type View } from "./SpendingParts";

type Drill = { title: string; filter: SpendFilter; from: "category" | "who" | "merchants" } | null;

const PERSON: Record<string, string> = { Joint: "Shared" };
const COUNTRY: Record<string, string> = { EC: "Ecuador", US: "United States" };
const FIXED: Record<string, string> = { fixed: "Fixed", variable: "Variable" };

/** "+12% (+120.00)" / "−5% (−40.00)" / "new" / "—" — the change from a previous amount. */
export function change(now: string | number, before: string | number): string {
  const a = num(now);
  const b = num(before);
  if (!b) return a ? "new" : "—";
  const d = a - b;
  const pctText = `${d >= 0 ? "+" : "−"}${Math.abs(Math.round((d / b) * 100))}%`;
  return `${pctText} (${d >= 0 ? "+" : "−"}${money(Math.abs(d))})`;
}

/** "9% more than August" / "5% less than September 2025" / "the same as …". */
export function compareWords(now: string | number, before: string | number, label: string): string | null {
  const a = num(now);
  const b = num(before);
  if (!b) return null;
  const p = Math.round(((a - b) / b) * 100);
  if (p === 0) return `about the same as ${label}`;
  return `${Math.abs(p)}% ${p > 0 ? "more" : "less"} than ${label}`;
}

const prevMonth = (iso: string) => {
  const { year, month } = parts(iso);
  return month === 1 ? `${year - 1}-12-01` : `${year}-${String(month - 1).padStart(2, "0")}-01`;
};
const yearAgo = (iso: string) => `${parts(iso).year - 1}${iso.slice(4)}`;

export function headline(s: Spending, today: string = localToday()): string {
  if (s.source === "none") return "Spending";
  if (s.month.slice(0, 7) === today.slice(0, 7)) {
    // The month isn't over: comparing part of it with whole months would mislead.
    const day = Number(today.slice(8, 10));
    return `So far in ${monthLong(s.month)} (day ${day}) you spent ${money(s.total.amount)}.`;
  }
  const words = [
    compareWords(s.total.amount, s.total.prev, monthLong(prevMonth(s.month)).split(" ")[0]),
    compareWords(s.total.amount, s.total.last_year, monthLong(yearAgo(s.month))),
  ].filter(Boolean);
  return `In ${monthLong(s.month)} you spent ${money(s.total.amount)}${words.length ? `: ${words.join(", ")}` : ""}.`;
}

export default function SpendingPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? `${raw}-01` : null;
  const [person, , ready] = usePerson();
  const q = useQuery({
    queryKey: ["spending", month, person],
    queryFn: () => fetchSpending(month, personParam(person)),
    enabled: ready,
  });
  const [drill, setDrill] = useState<Drill>(null);
  const [open, setOpen] = useState<number | null>(null);
  const s = q.data;
  const view: View = (params.get("view") as View) in VIEWS ? (params.get("view") as View) : "groups";
  const g = params.get("g") === null ? null : Number(params.get("g"));
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)));
    setParams(next);
  };
  const go = (m: string) => {
    setDrill(null);
    setOpen(null);
    set({ month: m.slice(0, 7), g: null });
  };
  const who = personParam(person);
  const group = s?.groups.find((x) => x.group_id === g);
  const fixed = s?.fixed.find((x) => x.key === "fixed");
  const variable = s?.fixed.find((x) => x.key === "variable");
  const unexplained = s?.groups.find((x) => x.group_id === 0);
  const idx = s ? s.months.indexOf(s.month) : -1;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">{s ? headline(s) : "Spending"}</h1>
      <p className="mt-2 text-lg text-muted">
        Expenses, fees and interest less refunds; transfers and card payments are left out, like the
        Overview’s spending view.
      </p>
      {s && s.source !== "none" && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <ExportLinks
            dataset="spending_lines"
            label={`${monthLong(s.month)} lines`}
            month={s.month.slice(0, 7)}
          />
          <SaveView month={monthLong(s.month)} />
        </div>
      )}
      <PersonNote person={person} />
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load spending: {(q.error as Error).message}
        </p>
      )}
      {!s && !q.error && <p className="mt-6 text-muted">Adding up the month…</p>}
      {s && s.source === "none" && (
        <p className="mt-6 rounded-2xl bg-info-bg px-5 py-4">
          No spending loaded yet.{" "}
          <Link className="text-primary underline" to="/import">
            Load the Excel history or upload statements
          </Link>
          .
        </p>
      )}
      {s && s.source !== "none" && (
        <>
          <div className="mt-6 flex flex-wrap items-end gap-3">
            <button
              className="btn btn-quiet h-11 px-3"
              disabled={idx < 0 || idx >= s.months.length - 1}
              onClick={() => go(s.months[idx + 1])}
            >
              ← Earlier
            </button>
            <label>
              <span className="label">Month</span>
              <select className="field w-52" value={s.month} onChange={(e) => go(e.target.value)}>
                {s.months.map((m) => (
                  <option key={m} value={m}>
                    {monthLong(m)}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn btn-quiet h-11 px-3"
              disabled={idx <= 0}
              onClick={() => go(s.months[idx - 1])}
            >
              Later →
            </button>
            {s.source === "excel" && (
              <span className="pill pill-muted">From the Cash Flow sheet: categories, no merchants</span>
            )}
            <div className="ml-auto">
              <ViewSwitch
                view={view}
                onChange={(v) => {
                  setDrill(null);
                  set({ view: v === "groups" ? null : v, pg: null });
                }}
              />
            </div>
          </div>

          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiCard
              label="Spent"
              value={money(s.total.amount)}
              note={
                s.month.slice(0, 7) === localToday().slice(0, 7)
                  ? `${s.total.transactions} lines so far; the month isn't over`
                  : `${change(s.total.amount, s.total.prev)} vs ${monthShort(prevMonth(s.month))} · ${s.total.transactions} lines`
              }
            />
            <KpiCard
              label="Fixed"
              value={money(fixed?.amount ?? 0)}
              note={`${fixed?.transactions ?? 0} lines: mortgage, daycare, insurance, staff`}
            />
            <KpiCard
              label="Variable"
              value={money(variable?.amount ?? 0)}
              note={`${variable?.transactions ?? 0} lines: where savings usually are`}
            />
            <KpiCard
              label="Not yet explained"
              value={money(unexplained?.amount ?? 0)}
              note={`${unexplained?.transactions ?? 0} lines without a category`}
              tone={unexplained && num(unexplained.amount) > 0 ? "attention" : undefined}
            />
          </dl>
          <p className="mt-2 text-sm text-muted">
            vs {monthShort(s.month)} {parts(s.month).year - 1}: {change(s.total.amount, s.total.last_year)}
          </p>

          {view === "groups" && (
            <>
              <GroupMap
                s={s}
                onPick={(id) => {
                  setOpen(id);
                  set({ g: String(id) });
                }}
              />
              {group && s.source !== "excel" && (
                <>
                  <nav aria-label="Drill path" className="mt-6 flex flex-wrap items-center gap-2 text-sm">
                    <button
                      type="button"
                      className="font-semibold text-primary underline"
                      onClick={() => set({ g: null })}
                    >
                      All spending
                    </button>
                    <span aria-hidden className="text-muted">
                      ›
                    </span>
                    <strong aria-current="location">{group.name}</strong>
                    {group.name === "Groceries" && (
                      <Link
                        to={`/groceries?month=${s.month.slice(0, 7)}`}
                        className="btn btn-primary ml-auto h-9 px-4 text-sm"
                      >
                        What it bought, product by product →
                      </Link>
                    )}
                  </nav>
                  <MerchantTable
                    month={s.month}
                    person={who}
                    groupId={group.group_id}
                    title={`${group.name}: ${money(group.amount)} in ${monthLong(s.month)}`}
                    onOpen={(m) => setDrill({ title: m, filter: { merchant: m }, from: "merchants" })}
                  />
                  {drill?.from === "merchants" && (
                    <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
                  )}
                </>
              )}
              <h2 className="mt-10 font-display text-2xl font-bold">By category</h2>
              <CategoryTable s={s} open={open} setOpen={setOpen} setDrill={setDrill} />
              {drill?.from === "category" && (
                <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
              )}
            </>
          )}

          {view === "merchants" && (
            <>
              <MerchantTable
                month={s.month}
                person={who}
                groupId={group?.group_id}
                title={group ? `${group.name} merchants` : `Merchants in ${monthLong(s.month)}`}
                onOpen={(m) => setDrill({ title: m, filter: { merchant: m }, from: "merchants" })}
              />
              {group && (
                <button type="button" className="btn btn-quiet mt-2" onClick={() => set({ g: null })}>
                  Every group
                </button>
              )}
              {drill?.from === "merchants" && (
                <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
              )}
            </>
          )}

          {view === "products" && (
            <ProductTable month={s.month} group={params.get("pg")} onGroup={(pg) => set({ pg })} />
          )}

          {view === "fixed" && (
            <>
              <h2 className="mt-10 font-display text-2xl font-bold">Who, where, fixed or variable</h2>
              <div className="mt-3 grid gap-4 md:grid-cols-3">
                <Breakdown
                  title="By person"
                  slices={s.by_person}
                  names={PERSON}
                  total={s.total.amount}
                  onPick={(x) =>
                    setDrill({ title: `${PERSON[x.key] ?? x.key}`, filter: { person: x.key }, from: "who" })
                  }
                />
                <Breakdown
                  title="By country"
                  slices={s.by_country}
                  names={COUNTRY}
                  total={s.total.amount}
                  onPick={(x) =>
                    setDrill({ title: COUNTRY[x.key] ?? x.key, filter: { country: x.key }, from: "who" })
                  }
                />
                <Breakdown
                  title="Fixed or variable"
                  slices={s.fixed}
                  names={FIXED}
                  total={s.total.amount}
                  onPick={(x) =>
                    setDrill({
                      title: `${FIXED[x.key]} spending`,
                      filter: { fixed: x.key === "fixed" },
                      from: "who",
                    })
                  }
                />
              </div>
              {drill?.from === "who" && (
                <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
              )}
            </>
          )}

          <Ideas month={s.month} person={who} />

          <h2 className="mt-10 font-display text-2xl font-bold">Spending over time</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <SpendingChart month={s.month} person={who} onSelect={(m) => s.months.includes(m) && go(m)} />
          </div>
        </>
      )}
    </section>
  );
}

function Swatch({ color }: { color: string | null }) {
  return (
    <span
      aria-hidden
      className="mr-2 inline-block h-3 w-3 rounded-full align-middle"
      style={{ background: color ?? "var(--color-muted)" }}
    />
  );
}

function CompareCells({ row }: { row: SpendCompare }) {
  return (
    <>
      <td className="num px-3 py-2 text-right">{money(row.amount)}</td>
      <td className="num hidden px-3 py-2 text-right text-muted md:table-cell">
        {change(row.amount, row.prev)}
      </td>
      <td className="num hidden px-3 py-2 text-right text-muted md:table-cell">
        {change(row.amount, row.last_year)}
      </td>
    </>
  );
}

function CategoryTable({
  s,
  open,
  setOpen,
  setDrill,
}: {
  s: Spending;
  open: number | null;
  setOpen: (id: number | null) => void;
  setDrill: (d: Drill) => void;
}) {
  const max = Math.max(1, ...s.groups.map((g) => num(g.amount)));
  return (
    <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
      <table className="w-full text-sm">
        <caption className="sr-only">Spending by category in {monthLong(s.month)}</caption>
        <thead className="bg-surface text-muted">
          <tr>
            <th scope="col" className="px-4 py-2 text-left font-semibold">
              Category
            </th>
            <th scope="col" className="px-3 py-2 text-right font-semibold">
              {monthShort(s.month)}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-right font-semibold md:table-cell">
              vs {monthShort(prevMonth(s.month))}
              {s.month.slice(0, 7) === localToday().slice(0, 7) && " (whole month)"}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-right font-semibold md:table-cell">
              vs {monthShort(s.month)} {parts(s.month).year - 1}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {s.groups.map((g) => {
            const isOpen = open === g.group_id;
            const share = Math.max(0, num(g.amount)) / max;
            return (
              <Fragment key={g.group_id}>
                <tr>
                  <th scope="row" className="px-4 py-2 text-left font-medium">
                    <button
                      className="flex w-full items-center text-left"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? null : g.group_id)}
                    >
                      <span aria-hidden className="mr-1 inline-block w-3 text-muted">
                        {isOpen ? "▾" : "▸"}
                      </span>
                      <Swatch color={g.color} />
                      <span className="min-w-0 flex-1">
                        {g.name}
                        <span
                          aria-hidden
                          className="mt-1 block h-1.5 rounded-full"
                          style={{ width: `${share * 100}%`, background: g.color ?? "var(--color-muted)" }}
                        />
                      </span>
                    </button>
                  </th>
                  <CompareCells row={g} />
                </tr>
                {isOpen &&
                  g.categories.map((c) => (
                    <tr key={c.category_id}>
                      <th scope="row" className="py-1.5 pl-12 pr-4 text-left font-normal">
                        <button
                          className="text-left text-primary underline-offset-2 hover:underline"
                          onClick={() =>
                            setDrill({
                              title: `${g.name} / ${c.name}`,
                              filter: { group_id: g.group_id, category_id: c.category_id },
                              from: "category",
                            })
                          }
                        >
                          {c.name}
                        </button>
                        <span className="text-xs text-muted">
                          {" "}
                          · {c.transactions} {c.transactions === 1 ? "line" : "lines"}
                        </span>
                      </th>
                      <CompareCells row={c} />
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Breakdown({
  title,
  slices,
  names,
  total,
  onPick,
}: {
  title: string;
  slices: SpendSlice[];
  names: Record<string, string>;
  total: string;
  onPick: (s: SpendSlice) => void;
}) {
  const t = Math.max(1, num(total));
  return (
    <section className="rounded-2xl border border-line p-4" aria-label={title}>
      <h3 className="font-semibold">{title}</h3>
      <ul className="mt-2 space-y-2">
        {slices.map((x) => (
          <li key={x.key}>
            <button className="w-full text-left" onClick={() => onPick(x)}>
              <span className="flex justify-between gap-2">
                <span className="underline-offset-2 hover:underline">{names[x.key] ?? x.key}</span>
                <span className="num">
                  {money(x.amount)}{" "}
                  <span className="text-muted">· {Math.round((num(x.amount) / t) * 100)}%</span>
                </span>
              </span>
              <span
                aria-hidden
                className="mt-1 block h-1.5 rounded-full bg-primary"
                style={{ width: `${Math.max(0, Math.min(1, num(x.amount) / t)) * 100}%` }}
              />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Lines({ month, drill, onClose }: { month: string; drill: NonNullable<Drill>; onClose: () => void }) {
  const [person] = usePerson();
  const who = personParam(person);
  const filter = who && !drill.filter.person ? { person: who, ...drill.filter } : drill.filter;
  const q = useQuery({
    queryKey: ["spending", "lines", month, filter],
    queryFn: () => fetchSpendLines(month, filter),
  });
  const total = (q.data ?? []).reduce((sum, l) => sum + num(l.amount), 0);
  const [fix, setFix] = useState(false);
  const f = drill.filter;
  const canFix = f.category_id !== undefined || f.group_id !== undefined;
  return (
    <section className="mt-6 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Lines: ${drill.title}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">
          {drill.title} · {monthLong(month)}
        </h2>
        <span className="flex gap-2">
          {canFix && (
            <button className="btn btn-primary h-9 px-3" onClick={() => setFix(true)}>
              Fix or find lines
            </button>
          )}
          <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
            Close
          </button>
        </span>
      </div>
      {fix && (
        <LinesPanel
          target={{
            title: drill.title,
            month,
            filter: {
              ...(f.category_id !== undefined ? { category_id: f.category_id } : { group_id: f.group_id }),
              side: "out",
              ...(who ? { person: who } : {}),
            },
            moveTo: f.category_id ?? null,
          }}
          onClose={() => setFix(false)}
        />
      )}
      {!q.data && <p className="mt-2 text-muted">Loading the lines…</p>}
      {q.data && (
        <>
          <p className="mt-1 text-muted">
            {q.data.length} {q.data.length === 1 ? "line" : "lines"} ·{" "}
            <span className="num">{money(total)}</span> ·{" "}
            <Link className="text-primary underline" to={`/transactions?month=${month.slice(0, 7)}`}>
              Edit in Transactions
            </Link>
          </p>
          <ul className="mt-3 divide-y divide-line">
            {q.data.map((l) => (
              <li key={l.transaction_id} className="flex items-center justify-between gap-3 py-1.5">
                <span className="min-w-0">
                  <span className="num">
                    {new Date(`${l.txn_date}T00:00:00`).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <span className="text-muted">
                    {" "}
                    · {l.account_name ?? (l.source === "excel_history" ? "Cash Flow sheet" : "—")} ·{" "}
                    {l.category_name}
                    {l.person !== "Joint" ? ` · ${l.person}` : ""}
                  </span>
                  <span className="block truncate font-mono text-xs">{l.description}</span>
                </span>
                <span className="num shrink-0">
                  {num(l.amount) < 0 ? `+${money(-num(l.amount))}` : money(l.amount)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
