import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchGroceryTrends, type GroceryMover, type GroceryRegular, type GroceryTrends } from "../api";
import { Legend, MonthBars, StackedColumns } from "../components/charts";
import { addMonths, money, monthLong, monthShort, num, pct } from "../money";

// Groceries → Trends (ADR-067): a year of supermarket spending by aisle, any two months side by
// side by aisle, type or brand, and the patterns in it: trips and basket, shopping days, prices
// that moved, new products and regulars not bought this month.

const SHOWN = 7; // aisles with their own color; the rest share one
const OTHER = "Everything else";
const COLORS = [
  "var(--color-cat-groceries)",
  "var(--color-cat-transport)",
  "var(--color-cat-dining)",
  "var(--color-cat-services)",
  "var(--color-cat-delivery)",
  "var(--color-cat-shopping)",
  "var(--color-cat-health)",
];
const OTHER_COLOR = "var(--color-cat-fixed)";
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const LONG_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const PERIODS = [6, 12, 24];
type Dim = "aisle" | "type" | "brand";
const DIMS: [Dim, string][] = [
  ["aisle", "Aisle"],
  ["type", "Type of product"],
  ["brand", "Brand"],
];
const NO_LABEL: Record<Dim, string> = {
  aisle: "Not grouped yet",
  type: "No type yet",
  brand: "No brand yet",
};

const signedPct = (v: number) => `${v > 0 ? "+" : ""}${pct(v)}`;
const round = (v: string | number) => money(v).replace(/\.\d\d$/, "");

export default function GroceryTrends({ month }: { month: string }) {
  const [params, setParams] = useSearchParams();
  const months = PERIODS.includes(Number(params.get("months"))) ? Number(params.get("months")) : 12;
  const q = useQuery({
    queryKey: ["groceries", "trends", month, months],
    queryFn: () => fetchGroceryTrends(`${month}-01`, months),
  });
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v === null) next.delete(k);
    else next.set(k, v);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted">
          Columns are what the supermarket invoices bought, by aisle; the dark line is the Groceries spending
          on your statements. Click a month to look at it.
        </p>
        <div role="radiogroup" aria-label="Period" className="flex rounded-[10px] bg-surface p-1 text-sm">
          {PERIODS.map((n) => (
            <button
              key={n}
              role="radio"
              aria-checked={months === n}
              onClick={() => set("months", n === 12 ? null : String(n))}
              className={`rounded-lg px-3 py-1.5 font-semibold ${months === n ? "bg-ground shadow-sm" : "text-muted"}`}
            >
              {n} months
            </button>
          ))}
        </div>
      </div>
      {q.error && (
        <p role="alert" className="card border-danger-ink p-4 text-danger-ink">
          {(q.error as Error).message}
        </p>
      )}
      {!q.data && !q.error && <p className="text-muted">Loading…</p>}
      {q.data && <Body t={q.data} month={month} onMonth={(m) => set("month", m)} />}
    </div>
  );
}

function Body({ t, month, onMonth }: { t: GroceryTrends; month: string; onMonth: (m: string) => void }) {
  const shown = t.aisles.filter((a) => a !== NO_LABEL.aisle).slice(0, SHOWN);
  const color = (a: string) => {
    const i = shown.indexOf(a);
    return i < 0 ? OTHER_COLOR : COLORS[i];
  };
  const hasOther = t.aisles.some((a) => !shown.includes(a));
  const data = t.months.map((m) => {
    const other = Object.entries(m.aisles)
      .filter(([a]) => !shown.includes(a))
      .reduce((s, [, v]) => s + num(v), 0);
    return {
      key: m.month.slice(0, 7),
      label: monthShort(m.month),
      selected: m.month.slice(0, 7) === month,
      line: num(m.spent) > 0 ? num(m.spent) : undefined,
      segments: [
        ...shown.map((a) => ({ key: a, value: num(m.aisles[a]), color: color(a) })),
        { key: OTHER, value: other, color: OTHER_COLOR },
      ],
      tooltip: (
        <>
          <p className="font-semibold">{monthLong(m.month)}</p>
          <p className="num">Spent {money(m.spent)}</p>
          <p className="num text-muted">
            Invoices {money(m.invoiced)} · {m.trips} trips
          </p>
        </>
      ),
    };
  });

  return (
    <>
      <Kpis t={t} month={month} />
      <section aria-labelledby="by-month" className="card space-y-4 p-5">
        <h2 id="by-month" className="font-display text-xl font-bold">
          Month by month, by aisle
        </h2>
        <StackedColumns data={data} title="Grocery spending by aisle each month" onSelect={onMonth} />
        <div className="flex flex-wrap items-center gap-4">
          <Legend
            items={[
              ...shown.map((a) => ({ label: a, color: color(a) })),
              ...(hasOther ? [{ label: OTHER, color: OTHER_COLOR }] : []),
            ]}
          />
          <span className="flex items-center gap-2 text-sm text-muted">
            <span aria-hidden className="inline-block h-0.5 w-5 bg-ink" /> Spent (statements)
          </span>
        </div>
        <MonthTable t={t} month={month} />
      </section>
      <Compare t={t} month={month} />
      <div className="grid gap-6 lg:grid-cols-2">
        <VsUsual t={t} month={month} />
        <Days t={t} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Movers
          title="Prices that went up"
          rows={t.risers}
          empty="No product costs more than when you first bought it."
        />
        <Movers
          title="Prices that went down"
          rows={t.fallers}
          empty="No product got cheaper in this period."
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Regulars
          title={`New in ${monthLong(`${month}-01`)}`}
          note="Bought for the first time in the period."
          rows={t.new}
          empty="Nothing new this month."
          amount={(r) => money(r.usual)}
        />
        <Regulars
          title="Regulars you didn't buy this month"
          note="Bought in at least 3 of the 6 months before, but not this month."
          rows={t.skipped}
          empty="You bought all your regulars."
          amount={(r) => `${r.months} of 6 · ${money(r.usual)}`}
        />
      </div>
    </>
  );
}

function Kpis({ t, month }: { t: GroceryTrends; month: string }) {
  const withData = t.months.filter((m) => num(m.spent) > 0);
  const avg = withData.length ? withData.reduce((s, m) => s + num(m.spent), 0) / withData.length : 0;
  const high = withData.reduce<(typeof withData)[number] | null>(
    (b, m) => (!b || num(m.spent) > num(b.spent) ? m : b),
    null,
  );
  const low = withData.reduce<(typeof withData)[number] | null>(
    (b, m) => (!b || num(m.spent) < num(b.spent) ? m : b),
    null,
  );
  const tripMonths = t.months.filter((m) => m.trips > 0);
  const trips = tripMonths.length ? tripMonths.reduce((s, m) => s + m.trips, 0) / tripMonths.length : 0;
  const basket =
    tripMonths.length > 0
      ? tripMonths.reduce((s, m) => s + num(m.invoiced), 0) / tripMonths.reduce((s, m) => s + m.trips, 0)
      : 0;
  const now = t.months.find((m) => m.month.slice(0, 7) === month);
  const busiest = t.weekdays.reduce((b, d) => (d.trips > b.trips ? d : b), t.weekdays[0]);
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Tile label="Average month" value={avg ? money(avg) : "—"}>
        {withData.length} months with statements
      </Tile>
      <Tile label="Highest and lowest" value={high ? round(high.spent) : "—"}>
        {high && low
          ? `${monthLong(high.month)} · lowest ${round(low.spent)} in ${monthShort(low.month)}`
          : "No months yet"}
      </Tile>
      <Tile label="Trips a month" value={trips ? trips.toFixed(1) : "—"}>
        {now ? `${now.trips} this month · ` : ""}average basket {money(basket)}
      </Tile>
      <Tile label="Usual shopping day" value={busiest && busiest.trips ? LONG_DAYS[busiest.day] : "—"}>
        {busiest && busiest.trips
          ? `${busiest.trips} of your invoices are from a ${LONG_DAYS[busiest.day]}`
          : "No invoices yet"}
      </Tile>
    </div>
  );
}

function Tile({ label, value, children }: { label: string; value: string; children: ReactNode }) {
  return (
    <div className="card p-5">
      <p className="label">{label}</p>
      <p className="num mt-1 font-display text-3xl font-bold">{value}</p>
      <p className="mt-1 text-sm text-muted">{children}</p>
    </div>
  );
}

function MonthTable({ t, month }: { t: GroceryTrends; month: string }) {
  return (
    <details>
      <summary className="cursor-pointer text-sm font-semibold text-primary">
        The numbers, month by month
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-muted">
            <tr>
              {["Month", "Spent", "With invoices", "Trips", "Basket", "Top aisle"].map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  className={`px-2 py-1 font-semibold ${i === 0 || i === 5 ? "text-left" : "text-right"}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {t.months
              .slice()
              .reverse()
              .map((m) => {
                const top = Object.entries(m.aisles).sort((a, b) => num(b[1]) - num(a[1]))[0];
                return (
                  <tr key={m.month} className={m.month.slice(0, 7) === month ? "font-semibold" : ""}>
                    <td className="px-2 py-1.5">{monthLong(m.month)}</td>
                    <td className="num px-2 py-1.5 text-right">{money(m.spent)}</td>
                    <td className="num px-2 py-1.5 text-right">{money(m.invoiced)}</td>
                    <td className="num px-2 py-1.5 text-right">{m.trips}</td>
                    <td className="num px-2 py-1.5 text-right">{m.trips ? money(m.basket) : "—"}</td>
                    <td className="px-2 py-1.5 text-muted">{top ? `${top[0]} · ${money(top[1])}` : "—"}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** Any two months side by side, by aisle, type of product or brand. */
function Compare({ t, month }: { t: GroceryTrends; month: string }) {
  const list = t.months.map((m) => m.month.slice(0, 7));
  const [b, setB] = useState(list.includes(month) ? month : list[list.length - 1]);
  const [a, setA] = useState(addMonths(`${b}-01`, -1).slice(0, 7));
  const [dim, setDim] = useState<Dim>("aisle");
  const rows = useMemo(() => {
    const by = new Map<string, [number, number]>();
    for (const c of t.cells) {
      const m = c.month.slice(0, 7);
      if (m !== a && m !== b) continue;
      const name = (dim === "aisle" ? c.aisle : c[dim]) ?? NO_LABEL[dim];
      const r = by.get(name) ?? [0, 0];
      if (m === a) r[0] += num(c.amount);
      if (m === b) r[1] += num(c.amount);
      by.set(name, r);
    }
    return [...by.entries()]
      .map(([name, [x, y]]) => ({ name, a: x, b: y, d: y - x }))
      .sort((p, q) => Math.abs(q.d) - Math.abs(p.d));
  }, [t.cells, a, b, dim]);
  const total = rows.reduce((s, r) => [s[0] + r.a, s[1] + r.b], [0, 0]);
  const maxD = Math.max(1, ...rows.map((r) => Math.abs(r.d)));
  const pick = (label: string, value: string, on: (v: string) => void) => (
    <label>
      <span className="label">{label}</span>
      <select className="field w-44" value={value} onChange={(e) => on(e.target.value)}>
        {list.map((m) => (
          <option key={m} value={m}>
            {monthLong(`${m}-01`)}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <section aria-labelledby="compare" className="card space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="compare" className="font-display text-xl font-bold">
            Compare two months
          </h2>
          <p className="text-sm text-muted">From the invoices; biggest change first.</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {pick("Month A", a, setA)}
          {pick("Month B", b, setB)}
          <div
            role="radiogroup"
            aria-label="Compare by"
            className="flex rounded-[10px] bg-surface p-1 text-sm"
          >
            {DIMS.map(([d, name]) => (
              <button
                key={d}
                role="radio"
                aria-checked={dim === d}
                onClick={() => setDim(d)}
                className={`rounded-lg px-3 py-1.5 font-semibold ${dim === d ? "bg-ground shadow-sm" : "text-muted"}`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No supermarket invoices in either month.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted">
              <tr>
                <th scope="col" className="px-2 py-1 text-left font-semibold">
                  {DIMS.find(([d]) => d === dim)![1]}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  {monthShort(`${a}-01`)} {a.slice(0, 4)}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  {monthShort(`${b}-01`)} {b.slice(0, 4)}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Change
                </th>
                <th scope="col" className="hidden w-48 px-2 py-1 sm:table-cell">
                  <span className="sr-only">Change, drawn</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.slice(0, 25).map((r) => (
                <tr key={r.name}>
                  <td className="max-w-64 truncate px-2 py-1.5" title={r.name}>
                    {r.name}
                  </td>
                  <td className="num px-2 py-1.5 text-right">{money(r.a)}</td>
                  <td className="num px-2 py-1.5 text-right">{money(r.b)}</td>
                  <td
                    className={`num px-2 py-1.5 text-right ${r.d > 0.005 ? "text-danger-ink" : r.d < -0.005 ? "text-good-ink" : "text-muted"}`}
                  >
                    {r.d > 0 ? "+" : ""}
                    {money(r.d)}
                    {r.a > 0 && <span className="block text-xs">{signedPct(r.d / r.a)}</span>}
                    {r.a === 0 && r.b > 0 && <span className="block text-xs">new</span>}
                  </td>
                  <td className="hidden px-2 py-1.5 sm:table-cell">
                    <div className="relative h-2.5">
                      <span aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-line" />
                      <span
                        aria-hidden
                        className={`absolute inset-y-0 rounded-sm ${r.d >= 0 ? "left-1/2 bg-danger-ink" : "right-1/2 bg-good-ink"}`}
                        style={{ width: `${(Math.abs(r.d) / maxD) * 50}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-line font-semibold">
              <tr>
                <td className="px-2 py-1.5">Total</td>
                <td className="num px-2 py-1.5 text-right">{money(total[0])}</td>
                <td className="num px-2 py-1.5 text-right">{money(total[1])}</td>
                <td className="num px-2 py-1.5 text-right">
                  {total[1] - total[0] > 0 ? "+" : ""}
                  {money(total[1] - total[0])}
                </td>
                <td className="hidden sm:table-cell" />
              </tr>
            </tfoot>
          </table>
          {rows.length > 25 && (
            <p className="mt-2 text-xs text-muted">The 25 biggest changes of {rows.length}.</p>
          )}
        </div>
      )}
    </section>
  );
}

/** This month's aisles against their average of the three months before. */
function VsUsual({ t, month }: { t: GroceryTrends; month: string }) {
  const i = t.months.findIndex((m) => m.month.slice(0, 7) === month);
  const before = i > 0 ? t.months.slice(Math.max(0, i - 3), i).filter((m) => m.trips > 0) : [];
  const now = i >= 0 ? t.months[i] : null;
  const rows =
    now && before.length
      ? t.aisles
          .map((a) => {
            const usual = before.reduce((s, m) => s + num(m.aisles[a]), 0) / before.length;
            const v = num(now.aisles[a]);
            return { a, v, usual, d: v - usual };
          })
          .filter((r) => Math.abs(r.d) >= 1)
          .sort((p, q) => Math.abs(q.d) - Math.abs(p.d))
          .slice(0, 6)
      : [];
  return (
    <section aria-labelledby="vs-usual" className="card space-y-3 p-5">
      <div>
        <h2 id="vs-usual" className="font-display text-xl font-bold">
          {now ? monthLong(now.month) : "This month"} against your usual
        </h2>
        <p className="text-sm text-muted">Each aisle against its average of the 3 months before.</p>
      </div>
      {rows.length === 0 && (
        <p className="text-sm text-muted">Not enough months with invoices to compare yet.</p>
      )}
      <ul className="divide-y divide-line text-sm">
        {rows.map((r) => (
          <li key={r.a} className="flex items-baseline justify-between gap-3 py-2">
            <span className="min-w-0 truncate">
              {r.a}
              <span className="block text-xs text-muted">
                {money(r.v)} · usual {money(r.usual)}
              </span>
            </span>
            <span className={`num shrink-0 font-semibold ${r.d > 0 ? "text-danger-ink" : "text-good-ink"}`}>
              {r.d > 0 ? "+" : "−"}
              {money(Math.abs(r.d))}
              {r.usual > 0 && (
                <span className="block text-right text-xs font-normal">{signedPct(r.d / r.usual)}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Days({ t }: { t: GroceryTrends }) {
  const data = t.weekdays.map((d) => ({
    key: String(d.day),
    label: DAYS[d.day],
    value: num(d.amount),
    selected: true,
    tooltip: (
      <>
        <p className="font-semibold">{LONG_DAYS[d.day]}</p>
        <p className="num">
          {money(d.amount)} · {d.trips} trips
        </p>
      </>
    ),
  }));
  return (
    <section aria-labelledby="days" className="card space-y-3 p-5">
      <div>
        <h2 id="days" className="font-display text-xl font-bold">
          When you shop
        </h2>
        <p className="text-sm text-muted">Invoice amounts by day of the week, over the whole period.</p>
      </div>
      <MonthBars data={data} title="Grocery invoices by day of the week" />
      <table className="sr-only">
        <tbody>
          {t.weekdays.map((d) => (
            <tr key={d.day}>
              <th scope="row">{LONG_DAYS[d.day]}</th>
              <td>{money(d.amount)}</td>
              <td>{d.trips} trips</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Movers({ title, rows, empty }: { title: string; rows: GroceryMover[]; empty: string }) {
  return (
    <section aria-label={title} className="card space-y-3 p-5">
      <div>
        <h2 className="font-display text-xl font-bold">{title}</h2>
        <p className="text-sm text-muted">
          Unit price the first month you bought it in the period, and the last.
        </p>
      </div>
      {rows.length === 0 && <p className="text-sm text-muted">{empty}</p>}
      <ul className="divide-y divide-line text-sm">
        {rows.map((r) => {
          const ch = num(r.change);
          return (
            <li key={r.product_key} className="flex items-baseline justify-between gap-3 py-2">
              <span className="min-w-0">
                <span className="block truncate" title={r.description}>
                  {r.description}
                </span>
                <span className="num block text-xs text-muted">
                  {money(r.first_price)} in {monthShort(r.first_month)} → {money(r.last_price)} in{" "}
                  {monthShort(r.last_month)}
                </span>
              </span>
              <span className={`num shrink-0 font-semibold ${ch > 0 ? "text-danger-ink" : "text-good-ink"}`}>
                {signedPct(ch)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Regulars({
  title,
  note,
  rows,
  empty,
  amount,
}: {
  title: string;
  note: string;
  rows: GroceryRegular[];
  empty: string;
  amount: (r: GroceryRegular) => string;
}) {
  return (
    <section aria-label={title} className="card space-y-3 p-5">
      <div>
        <h2 className="font-display text-xl font-bold">{title}</h2>
        <p className="text-sm text-muted">{note}</p>
      </div>
      {rows.length === 0 && <p className="text-sm text-muted">{empty}</p>}
      <ul className="divide-y divide-line text-sm">
        {rows.map((r) => (
          <li key={r.product_key} className="flex items-baseline justify-between gap-3 py-2">
            <span className="min-w-0 truncate" title={r.description}>
              {r.description}
              <span className="block text-xs text-muted">{r.aisle}</span>
            </span>
            <span className="num shrink-0">{amount(r)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
