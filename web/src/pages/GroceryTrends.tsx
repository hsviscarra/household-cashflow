import ChartTools from "../components/ChartTools";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchGroceryTrends, type GroceryTrends } from "../api";
import { Legend, StackedColumns } from "../components/charts";
import { money, monthLong, monthShort, num } from "../money";
import { SHOWN, OTHER, COLORS, OTHER_COLOR, NO_LABEL } from "./groceries/shared";
import { Compare, VsUsual } from "./groceries/Compare";
import { Kpis, MonthTable, Days, Movers, Regulars } from "./groceries/Panels";

const PERIODS = [6, 12, 24];

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
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="by-month" className="font-display text-xl font-bold">
            Month by month, by aisle
          </h2>
          <ChartTools
            name="Groceries"
            csv={{
              file: "groceries-by-aisle.csv",
              rows: () => [
                ["Month", "Spent", "Invoiced", "Trips", ...t.aisles],
                ...t.months.map((m) => [
                  m.month.slice(0, 7),
                  num(m.spent).toFixed(2),
                  num(m.invoiced).toFixed(2),
                  m.trips,
                  ...t.aisles.map((a) => num(m.aisles[a]).toFixed(2)),
                ]),
              ],
            }}
            explain={`Explain our grocery spending over the last ${t.months.length} months: which aisles grew or shrank and anything unusual.`}
          />
        </div>
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
