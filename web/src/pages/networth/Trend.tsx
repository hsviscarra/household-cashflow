import { type BalanceSheet, fetchBalanceSheetOver } from "../../api";
import { useSettings, asRecord } from "../../prefs";
import { useQuery } from "@tanstack/react-query";
import ChartTools from "../../components/ChartTools";
import { num, monthLong, monthShort, money } from "../../money";
import { TrendLine } from "../../components/charts";

export const TREND_PERIODS = { "12": "12 months", "24": "24 months", "36": "36 months" };

export type TrendPeriod = keyof typeof TREND_PERIODS;

/** The trend with its own period (ADR-101): the sheet the page already has covers 24 months; any
 * other period is asked for. */
export function Trend({ s: sheet }: { s: BalanceSheet }) {
  const { settings, set } = useSettings();
  const saved = String(asRecord(settings["chart:networth"]).period);
  const period: TrendPeriod = saved in TREND_PERIODS ? (saved as TrendPeriod) : "24";
  const other = useQuery({
    queryKey: ["networth", "trend", period],
    queryFn: () => fetchBalanceSheetOver(Number(period)),
    enabled: period !== "24",
  });
  const s = period === "24" ? sheet : (other.data ?? sheet);
  return (
    <>
      <div className="mt-10 flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-display text-2xl font-bold">Net worth over time</h2>
        <ChartTools
          name="Net worth"
          period={{
            value: period,
            options: TREND_PERIODS,
            onChange: (p) => set("chart:networth", { period: p }),
          }}
          csv={{
            file: "net-worth.csv",
            rows: () => [
              ["Month", "Own", "Owe", "Net"],
              ...s.series.map((p) => [
                p.month.slice(0, 7),
                num(p.assets).toFixed(2),
                num(p.liabilities).toFixed(2),
                num(p.net).toFixed(2),
              ]),
            ],
          }}
          explain={`Explain how our net worth changed over the last ${period} months and what moved it most.`}
        />
      </div>
      <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
        <TrendLine
          title={`Net worth by month, ${monthLong(s.series[0].month)} to ${monthLong(s.series[s.series.length - 1].month)}`}
          data={s.series.map((p, i) => ({
            key: p.month,
            value: num(p.net),
            tick: i % 3 === 2 || i === s.series.length - 1 ? monthShort(p.month) : undefined,
            tooltip: (
              <>
                <strong>{monthLong(p.month)}</strong>
                <span className="num block">Net {money(p.net)}</span>
                <span className="num block text-muted">
                  Own {money(p.assets)} · owe {money(p.liabilities)}
                </span>
              </>
            ),
          }))}
        />
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-muted">The numbers</summary>
          <table className="mt-2 w-full">
            <caption className="sr-only">Assets, liabilities and net worth by month</caption>
            <thead className="text-muted">
              <tr>
                <th scope="col" className="py-1 text-left font-normal">
                  Month
                </th>
                <th scope="col" className="py-1 text-right font-normal">
                  Own
                </th>
                <th scope="col" className="py-1 text-right font-normal">
                  Owe
                </th>
                <th scope="col" className="py-1 text-right font-normal">
                  Net
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {s.series.map((p) => (
                <tr key={p.month}>
                  <th scope="row" className="py-1 text-left font-normal">
                    {monthLong(p.month)}
                  </th>
                  <td className="num py-1 text-right">{money(p.assets)}</td>
                  <td className="num py-1 text-right">{money(p.liabilities)}</td>
                  <td className="num py-1 text-right">{money(p.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
        <p className="mt-2 text-sm text-muted">
          Each month counts the values known on its last day: give an item the date you bought it so past
          months include it.
        </p>
      </div>
    </>
  );
}

export function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
      {hint && <dd className="text-xs text-muted">{hint}</dd>}
    </div>
  );
}
