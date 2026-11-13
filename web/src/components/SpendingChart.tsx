import { useQuery } from "@tanstack/react-query";

import { fetchSpendSeries, type SeriesBy, type SpendSeries } from "../api";
import { askAbout } from "../ask";
import { downloadText } from "../csv";
import { addMonths, money, monthLong, monthShort, num } from "../money";
import { asRecord, useSettings } from "../prefs";
import { Legend, StackedColumns } from "./charts";

// A chart with controls (ADR-094, plan item B3): the period, what to split by and how to show it
// are the person's choice and are remembered. The numbers come grouped from the server; the
// same numbers are always available as a table and as a CSV file.

const PERIODS = { "3": "3 months", "6": "6 months", "12": "12 months", "24": "24 months", ytd: "This year" };
const SPLITS: Record<SeriesBy, string> = {
  none: "Nothing",
  group: "Group",
  category: "Category",
  person: "Who",
  account: "Account",
  country: "Country",
};
const SHOWS = { amounts: "Amounts", share: "Share of the month", table: "Table" };
const COMPARES = { none: "Nothing", year: "A year earlier" };
type Period = keyof typeof PERIODS;
type Compare = keyof typeof COMPARES;
type Show = keyof typeof SHOWS;
export type ChartChoice = { period: Period; by: SeriesBy; show: Show; compare: Compare };
const DEFAULT: ChartChoice = { period: "12", by: "none", show: "amounts", compare: "none" };

// The category palette (design system): seven series, the rest together in cat-fixed.
const PALETTE = ["groceries", "transport", "dining", "health", "shopping", "services", "delivery"].map(
  (c) => `var(--color-cat-${c})`,
);
const REST_COLOR = "var(--color-cat-fixed)";
const REST = "Everything else";

/** The saved choice, with anything unknown replaced by the default. */
export function choice(saved: unknown): ChartChoice {
  const s = asRecord(saved);
  return {
    period: (s.period as string) in PERIODS ? (s.period as Period) : DEFAULT.period,
    by: (s.by as string) in SPLITS ? (s.by as SeriesBy) : DEFAULT.by,
    show: (s.show as string) in SHOWS ? (s.show as Show) : DEFAULT.show,
    compare: (s.compare as string) in COMPARES ? (s.compare as Compare) : DEFAULT.compare,
  };
}

/** How many months a period covers when it ends in `month` (this year: January to that month). */
export const monthsOf = (period: Period, month: string) =>
  period === "ytd" ? Number(month.slice(5, 7)) : Number(period);

const colorOf = (s: SpendSeries["series"][number], i: number, single: boolean) =>
  single ? "var(--color-primary)" : s.label === REST ? REST_COLOR : (s.color ?? PALETTE[i % PALETTE.length]);

/** The table of the chart as CSV: one row per month, one column per series, and the total. */
export function toCsv(data: SpendSeries, before?: number[]): string {
  const cell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const head = [
    "Month",
    ...data.series.map((s) => s.label),
    ...(data.series.length > 1 ? ["Total"] : []),
    ...(before ? ["A year earlier", "Change"] : []),
  ];
  const rows = data.months.map((m, i) => {
    const values = data.series.map((s) => num(s.values[i]));
    const total = values.reduce((a, b) => a + b, 0);
    return [
      m.slice(0, 7),
      ...values.map((v) => v.toFixed(2)),
      ...(values.length > 1 ? [total.toFixed(2)] : []),
      ...(before ? [before[i].toFixed(2), (total - before[i]).toFixed(2)] : []),
    ];
  });
  return [head, ...rows].map((r) => r.map(cell).join(",")).join("\n");
}

/** A difference with its sign: spending more reads "+", less reads "−". */
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v))}`;

export default function SpendingChart({
  month,
  person,
  onSelect,
}: {
  month: string;
  person?: string;
  onSelect?: (month: string) => void;
}) {
  const { settings, set } = useSettings();
  const c = choice(settings["chart:spending"]);
  const change = (part: Partial<ChartChoice>) => set("chart:spending", { ...c, ...part });
  const count = monthsOf(c.period, month);
  const q = useQuery({
    queryKey: ["spending", "series", month, count, c.by, person ?? ""],
    queryFn: () => fetchSpendSeries(month, count, c.by, person),
  });
  const data = q.data;
  // The same months a year earlier, as one line over the columns (ADR-095).
  const earlier = useQuery({
    queryKey: ["spending", "series", addMonths(month, -12), count, "none", person ?? ""],
    queryFn: () => fetchSpendSeries(addMonths(month, -12), count, "none", person),
    enabled: c.compare === "year",
  });
  const before =
    c.compare === "year" && earlier.data && data && earlier.data.months.length === data.months.length
      ? earlier.data.months.map((_, i) => earlier.data.series.reduce((t, s) => t + num(s.values[i]), 0))
      : undefined;
  const single = (data?.series.length ?? 0) <= 1;
  const totals = data ? data.months.map((_, i) => data.series.reduce((t, s) => t + num(s.values[i]), 0)) : [];
  const title = data
    ? `Spending by month${c.by === "none" ? "" : ` by ${SPLITS[c.by].toLowerCase()}`}, ${monthLong(data.months[0])} to ${monthLong(month)}`
    : "Spending by month";

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <Pick label="Period" value={c.period} options={PERIODS} onChange={(period) => change({ period })} />
        <Pick label="Split by" value={c.by} options={SPLITS} onChange={(by) => change({ by })} />
        <Pick label="Show" value={c.show} options={SHOWS} onChange={(show) => change({ show })} />
        <Pick
          label="Compare with"
          value={c.compare}
          options={COMPARES}
          onChange={(compare) => change({ compare })}
        />
        {data && (
          <span className="ml-auto flex items-center gap-2">
            <button
              type="button"
              className="btn btn-quiet h-10 px-3 text-sm"
              onClick={() => downloadText(`spending-${month.slice(0, 7)}.csv`, toCsv(data, before))}
            >
              Download CSV
            </button>
            <button
              type="button"
              className="btn btn-quiet h-10 px-3 text-sm"
              onClick={() => askAbout(`Explain this chart: ${title}. What changed and why?`)}
            >
              Explain
            </button>
          </span>
        )}
      </div>
      {(q.error ?? earlier.error) && (
        <p role="alert" className="mt-3 text-sm text-danger-ink">
          {((q.error ?? earlier.error) as Error).message}
        </p>
      )}
      {data && c.show !== "table" && (
        <div className="mt-4">
          <StackedColumns
            title={c.show === "share" ? `${title}, as a share of each month (%)` : title}
            onSelect={onSelect}
            data={data.months.map((m, i) => ({
              key: m,
              label: monthShort(m),
              selected: m === month,
              line: c.show === "amounts" ? before?.[i] : undefined,
              segments: data.series.map((s, j) => ({
                key: s.key,
                color: colorOf(s, j, single),
                value:
                  c.show === "share" && totals[i] > 0
                    ? (num(s.values[i]) / totals[i]) * 100
                    : num(s.values[i]),
              })),
              tooltip: (
                <>
                  <strong>{monthLong(m)}</strong>
                  {!single &&
                    data.series
                      .filter((s) => num(s.values[i]) !== 0)
                      .map((s) => (
                        <span key={s.key} className="num block">
                          {s.label} {money(s.values[i])}
                        </span>
                      ))}
                  <span className="num block font-semibold">{money(totals[i])}</span>
                  {before && (
                    <span className="num block text-muted">
                      {monthLong(addMonths(m, -12))} {money(before[i])} · {signed(totals[i] - before[i])}
                    </span>
                  )}
                </>
              ),
            }))}
          />
          {(!single || before) && (
            <Legend
              items={[
                ...(single
                  ? [{ label: "Spending", color: "var(--color-primary)" }]
                  : data.series.map((s, j) => ({ label: s.label, color: colorOf(s, j, single) }))),
                ...(before && c.show === "amounts"
                  ? [{ label: "A year earlier (line)", color: "var(--color-ink)" }]
                  : []),
              ]}
            />
          )}
        </div>
      )}
      {data && (
        <details className="mt-2 text-sm" open={c.show === "table"}>
          <summary className="cursor-pointer text-muted">The numbers</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full">
              <caption className="sr-only">{title}</caption>
              <thead className="text-muted">
                <tr>
                  <th scope="col" className="py-1 text-left font-semibold">
                    Month
                  </th>
                  {data.series.map((s) => (
                    <th key={s.key} scope="col" className="px-2 py-1 text-right font-semibold">
                      {s.label}
                    </th>
                  ))}
                  {!single && (
                    <th scope="col" className="py-1 text-right font-semibold">
                      Total
                    </th>
                  )}
                  {before && (
                    <>
                      <th scope="col" className="px-2 py-1 text-right font-semibold">
                        A year earlier
                      </th>
                      <th scope="col" className="py-1 text-right font-semibold">
                        Change
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.months.map((m, i) => (
                  <tr key={m}>
                    <th scope="row" className="py-1 text-left font-normal">
                      {monthLong(m)}
                    </th>
                    {data.series.map((s) => (
                      <td key={s.key} className="num px-2 py-1 text-right">
                        {money(s.values[i])}
                      </td>
                    ))}
                    {!single && <td className="num py-1 text-right font-semibold">{money(totals[i])}</td>}
                    {before && (
                      <>
                        <td className="num px-2 py-1 text-right text-muted">{money(before[i])}</td>
                        <td className="num py-1 text-right">{signed(totals[i] - before[i])}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function Pick<K extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: K;
  options: Record<K, string>;
  onChange: (value: K) => void;
}) {
  return (
    <label>
      <span className="label">{label}</span>
      <select className="field h-10 !w-auto" value={value} onChange={(e) => onChange(e.target.value as K)}>
        {(Object.entries(options) as [K, string][]).map(([k, text]) => (
          <option key={k} value={k}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}
