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
import { MonthBars } from "../components/charts";
import { money, monthLong, monthShort, num, parts } from "../money";

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

export function headline(s: Spending): string {
  if (s.source === "none") return "Spending";
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
  const q = useQuery({ queryKey: ["spending", month], queryFn: () => fetchSpending(month) });
  const [drill, setDrill] = useState<Drill>(null);
  const [open, setOpen] = useState<number | null>(null);
  const s = q.data;
  const go = (m: string) => {
    setDrill(null);
    setOpen(null);
    setParams({ month: m.slice(0, 7) });
  };
  const idx = s ? s.months.indexOf(s.month) : -1;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">{s ? headline(s) : "Spending"}</h1>
      <p className="mt-2 text-lg text-muted">
        Expenses, fees and interest less refunds; transfers and card payments are left out, like the
        Overview’s spending view.
      </p>
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
          </div>

          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Spent" value={money(s.total.amount)} />
            <Tile
              label={`vs ${monthShort(prevMonth(s.month))}`}
              value={change(s.total.amount, s.total.prev)}
            />
            <Tile
              label={`vs ${monthShort(s.month)} ${parts(s.month).year - 1}`}
              value={change(s.total.amount, s.total.last_year)}
            />
            <Tile label="Lines" value={String(s.total.transactions)} />
          </dl>

          <h2 className="mt-10 font-display text-2xl font-bold">By category</h2>
          <CategoryTable s={s} open={open} setOpen={setOpen} setDrill={setDrill} />
          {drill?.from === "category" && (
            <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
          )}

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
          {drill?.from === "who" && <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />}

          <h2 className="mt-10 font-display text-2xl font-bold">Top merchants</h2>
          {s.merchants.length ? (
            <ol
              className="mt-3 divide-y divide-line rounded-2xl border border-line"
              aria-label="Top merchants"
            >
              {s.merchants.map((m, i) => (
                <li key={m.merchant} className="flex items-center justify-between gap-3 px-4 py-2">
                  <button
                    className="min-w-0 text-left underline-offset-2 hover:underline"
                    onClick={() =>
                      setDrill({ title: m.merchant, filter: { merchant: m.merchant }, from: "merchants" })
                    }
                  >
                    <span className="num mr-2 text-muted">{i + 1}.</span>
                    <span className="font-medium">{m.merchant}</span>
                    <span className="text-sm text-muted">
                      {" "}
                      · {m.group_name} · {m.transactions} {m.transactions === 1 ? "line" : "lines"}
                    </span>
                  </button>
                  <span className="num shrink-0">{money(m.amount)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-muted">
              {s.source === "excel"
                ? "Months from the Cash Flow sheet have category rows, not merchants."
                : "No merchants this month."}
            </p>
          )}
          {drill?.from === "merchants" && (
            <Lines month={s.month} drill={drill} onClose={() => setDrill(null)} />
          )}

          <h2 className="mt-10 font-display text-2xl font-bold">The last 12 months</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <MonthBars
              title={`Spending by month, ${monthLong(s.trend[0].month)} to ${monthLong(s.month)}`}
              data={s.trend.map((t) => ({
                key: t.month,
                label: monthShort(t.month),
                value: num(t.amount),
                selected: t.month === s.month,
                tooltip: (
                  <>
                    <strong>{monthLong(t.month)}</strong>
                    <span className="num block">{money(t.amount)}</span>
                  </>
                ),
              }))}
              onSelect={(m) => s.months.includes(m) && go(m)}
            />
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-muted">The numbers</summary>
              <table className="mt-2 w-full">
                <caption className="sr-only">Spending by month</caption>
                <tbody className="divide-y divide-line">
                  {s.trend.map((t) => (
                    <tr key={t.month}>
                      <th scope="row" className="py-1 text-left font-normal">
                        {monthLong(t.month)}
                      </th>
                      <td className="num py-1 text-right">{money(t.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>
        </>
      )}
    </section>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
    </div>
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
  const q = useQuery({
    queryKey: ["spending", "lines", month, drill.filter],
    queryFn: () => fetchSpendLines(month, drill.filter),
  });
  const total = (q.data ?? []).reduce((sum, l) => sum + num(l.amount), 0);
  return (
    <section className="mt-6 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Lines: ${drill.title}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">
          {drill.title} · {monthLong(month)}
        </h2>
        <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
          Close
        </button>
      </div>
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
