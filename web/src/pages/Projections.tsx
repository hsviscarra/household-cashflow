import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchProjection, type Projection, type ProjectionMonth } from "../api";
import { TrendLine } from "../components/charts";
import { money, monthLong, monthShort, num } from "../money";

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const signedMoney = (v: string | number) =>
  `${num(v) < 0 ? "−" : num(v) > 0 ? "+" : ""}${money(Math.abs(num(v)))}`;

/** "Next 3 months: −5,016.63; lowest cash −2,231.66 on Jan 20, before Hernan (Salaries) on Jan 21." */
export function projectionHeadline(p: Projection): string {
  const net = p.months.reduce((sum, m) => sum + num(m.net), 0);
  let text = `Next ${p.months.length} months: ${signedMoney(net)}`;
  if (p.lowest) {
    text += `; lowest cash ${signedMoney(p.lowest.balance).replace(/^\+/, "")} on ${day(p.lowest.day)}`;
    if (p.next_payday) text += `, before ${p.next_payday.name} on ${day(p.next_payday.day)}`;
  }
  return `${text}.`;
}

export default function ProjectionsPage() {
  const q = useQuery({ queryKey: ["projections"], queryFn: fetchProjection });
  const p = q.data;
  const totals = p
    ? {
        income: p.months.reduce((s, m) => s + num(m.income), 0),
        out: p.months.reduce((s, m) => s + num(m.fixed) + num(m.variable) + num(m.purchases), 0),
      }
    : null;
  const short = p?.lowest && num(p.lowest.balance) < 0;
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {p ? projectionHeadline(p) : "Projections"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        From your recurring items, your usual variable spending and the purchase installments, starting from
        your bank balances.
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the projection: {(q.error as Error).message}
        </p>
      )}
      {!p && !q.error && <p className="mt-6 text-muted">Projecting the next months…</p>}
      {p && totals && (
        <>
          {short && (
            <p className="mt-4 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
              Cash runs short: {money(Math.abs(num(p.lowest!.balance)))} below zero on {day(p.lowest!.day)}.
              Move money in before then or delay a payment.
            </p>
          )}
          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile
              label="Cash today"
              value={money(p.start_cash)}
              hint={p.cash_as_of ? `bank statements to ${day(p.cash_as_of)}` : "no bank statement yet"}
            />
            <Tile label="Money in, 3 months" value={money(totals.income)} />
            <Tile label="Money out, 3 months" value={money(totals.out)} />
            <Tile
              label={`Cash at the end of ${monthShort(p.months[p.months.length - 1].month)}`}
              value={signedMoney(p.months[p.months.length - 1].end_cash).replace(/^\+/, "")}
            />
          </dl>

          <h2 className="mt-10 font-display text-2xl font-bold">Month by month</h2>
          <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
            <table className="w-full text-sm">
              <caption className="sr-only">Projection for the next {p.months.length} months</caption>
              <thead className="bg-surface text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">
                    &nbsp;
                  </th>
                  {p.months.map((m) => (
                    <th key={m.month} scope="col" className="px-3 py-2 text-right font-semibold">
                      {monthLong(m.month)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                <Row label="Income (recurring)" months={p.months} pick={(m) => money(m.income)} />
                <Row label="Fixed outflows (recurring)" months={p.months} pick={(m) => money(m.fixed)} />
                <Row label="Variable spending (average)" months={p.months} pick={(m) => money(m.variable)} />
                <Row label="Purchase installments" months={p.months} pick={(m) => money(m.purchases)} />
                <Row label="Net" months={p.months} pick={(m) => signedMoney(m.net)} strong />
                <Row
                  label="Cash at month end"
                  months={p.months}
                  pick={(m) => signedMoney(m.end_cash).replace(/^\+/, "")}
                  strong
                />
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-sm text-muted">
            Variable spending is the average of{" "}
            {p.average_months.length
              ? p.average_months.map((m) => monthShort(m)).join(", ")
              : "no complete month yet"}
            : money spent from the bank that no recurring item paid. Card purchases are in the card payments.{" "}
            <Link className="text-primary underline" to="/recurring">
              Change the recurring items
            </Link>
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {p.months.map((m) => (
              <details key={m.month} className="rounded-2xl border border-line p-3 text-sm">
                <summary className="cursor-pointer font-semibold">
                  {monthLong(m.month)} · {m.items.length} {m.items.length === 1 ? "item" : "items"}
                </summary>
                <ul className="mt-2 divide-y divide-line" aria-label={`Items in ${monthLong(m.month)}`}>
                  {m.items.map((e, i) => (
                    <li key={i} className="flex justify-between gap-2 py-1">
                      <span>
                        <span className="num">{day(e.day)}</span> <span className="text-muted">·</span>{" "}
                        {e.name}
                      </span>
                      <span className="num">{signedMoney(e.amount)}</span>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>

          <h2 className="mt-10 font-display text-2xl font-bold">Cash day by day</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <TrendLine
              title={`Projected cash from ${day(p.daily[0].day)} to ${day(p.daily[p.daily.length - 1].day)}`}
              data={p.daily.map((d) => ({
                key: d.day,
                value: num(d.balance),
                tick: d.day.endsWith("-01") ? monthShort(d.day) : undefined,
                tooltip: (
                  <>
                    <strong>{day(d.day)}</strong>
                    <span className="num block">{money(d.balance)}</span>
                  </>
                ),
              }))}
            />
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-muted">The numbers</summary>
              <table className="mt-2 w-full">
                <caption className="sr-only">Projected cash by day</caption>
                <tbody className="divide-y divide-line">
                  {p.daily.map((d) => (
                    <tr key={d.day}>
                      <th scope="row" className="py-1 text-left font-normal">
                        {day(d.day)}
                      </th>
                      <td className="num py-1 text-right">{money(d.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>

          <h2 className="mt-10 font-display text-2xl font-bold">Spending alerts</h2>
          {p.alerts.length ? (
            <ul
              className="mt-3 divide-y divide-line rounded-2xl border border-line"
              aria-label="Spending alerts"
            >
              {p.alerts.map((a) => (
                <li key={a.group_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                  <span>
                    <strong>{a.group_name}</strong>: <span className="num">{money(a.amount)}</span> in{" "}
                    {monthLong(a.month)},{" "}
                    {a.change != null ? `${Math.round(num(a.change) * 100)}% above` : "above"} its{" "}
                    <span className="num">{money(a.average)}</span> average
                  </span>
                  <Link className="text-primary underline" to={`/spending?month=${a.month.slice(0, 7)}`}>
                    See the spending
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-muted">No category is more than 30% above its recent average.</p>
          )}
        </>
      )}
    </section>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
      {hint && <dd className="text-xs text-muted">{hint}</dd>}
    </div>
  );
}

function Row({
  label,
  months,
  pick,
  strong,
}: {
  label: string;
  months: ProjectionMonth[];
  pick: (m: ProjectionMonth) => string;
  strong?: boolean;
}) {
  return (
    <tr className={strong ? "font-semibold" : ""}>
      <th scope="row" className="px-4 py-2 text-left font-medium">
        {label}
      </th>
      {months.map((m) => (
        <td key={m.month} className="num px-3 py-2 text-right">
          {pick(m)}
        </td>
      ))}
    </tr>
  );
}
