import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchDebt, type Debt } from "../api";
import { MonthBars } from "../components/charts";
import { money, monthLong, monthShort, num } from "../money";

/** "2026 so far: 68.01 in interest and 108.51 in fees." */
export function debtHeadline(d: Debt): string {
  const when = d.through.startsWith(String(new Date().getFullYear())) ? `${d.year} so far` : String(d.year);
  if (!num(d.interest) && !num(d.fees)) return `${when}: no interest or fees`;
  return `${when}: ${money(d.interest)} in interest and ${money(d.fees)} in fees`;
}

export function monthTotals(d: Debt): number[] {
  return d.months.map((m) => d.accounts.reduce((sum, a) => sum + num(a.by_month[m]), 0));
}

export default function DebtPage() {
  const [params, setParams] = useSearchParams();
  const year = Number(params.get("year")) || null;
  const q = useQuery({ queryKey: ["debt", year], queryFn: () => fetchDebt(year) });
  const [open, setOpen] = useState<string | null>(null);
  const d = q.data;
  const totals = d ? monthTotals(d) : [];
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {d ? debtHeadline(d) : "Debt & Net Worth"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        What borrowing and banking cost: card interest, and fees (bank fees, SOLCA, the tax on digital
        services), per account.
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the cost of debt: {(q.error as Error).message}
        </p>
      )}
      {!d && !q.error && <p className="mt-6 text-muted">Adding up interest and fees…</p>}
      {d && (
        <>
          <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Year">
            {d.years.map((y) => (
              <button
                key={y}
                aria-pressed={y === d.year}
                className={`btn ${y === d.year ? "bg-ink text-ground" : "btn-secondary"}`}
                onClick={() => setParams({ year: String(y) })}
              >
                {y}
              </button>
            ))}
          </div>
          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-3">
            <Tile label={`Interest, ${d.year}`} value={money(d.interest)} />
            <Tile label={`Fees, ${d.year}`} value={money(d.fees)} />
            <Tile label="Last 12 months" value={money(totals.reduce((a, b) => a + b, 0))} />
          </dl>

          {d.accounts.length === 0 ? (
            <p className="mt-6 rounded-2xl bg-good-bg px-4 py-3 text-good-ink">No interest or fees loaded.</p>
          ) : (
            <div className="mt-6 overflow-x-auto rounded-2xl border border-line">
              <table className="w-full text-sm">
                <caption className="sr-only">Interest and fees by account, {d.year}</caption>
                <thead className="bg-surface text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">
                      Account
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold">
                      Interest {d.year}
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-semibold">
                      Fees {d.year}
                    </th>
                    <th scope="col" className="hidden px-3 py-2 text-right font-semibold md:table-cell">
                      Last 12 months
                    </th>
                    <th scope="col" className="hidden px-3 py-2 text-right font-semibold md:table-cell">
                      Statement balance
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {d.accounts.map((a) => {
                    const key = a.name;
                    const isOpen = open === key;
                    return (
                      <Fragment key={key}>
                        <tr>
                          <th scope="row" className="px-4 py-2 text-left font-medium">
                            <button
                              className="text-left"
                              aria-expanded={isOpen}
                              onClick={() => setOpen(isOpen ? null : key)}
                            >
                              <span aria-hidden className="mr-1 inline-block w-3 text-muted">
                                {isOpen ? "▾" : "▸"}
                              </span>
                              {a.name}
                            </button>
                          </th>
                          <td className="num px-3 py-2 text-right">{money(a.interest)}</td>
                          <td className="num px-3 py-2 text-right">{money(a.fees)}</td>
                          <td className="num hidden px-3 py-2 text-right md:table-cell">
                            {money(a.last_12)}
                          </td>
                          <td className="num hidden px-3 py-2 text-right md:table-cell">
                            {a.balance != null ? (
                              <>
                                {money(a.balance)}
                                <span className="block text-xs text-muted">
                                  on{" "}
                                  {new Date(`${a.balance_date}T00:00:00`).toLocaleDateString("en-US", {
                                    month: "short",
                                    day: "numeric",
                                    year: "numeric",
                                  })}
                                </span>
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td colSpan={5} className="bg-surface px-4 py-3">
                              <AccountDetail d={d} name={key} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <h2 className="mt-10 font-display text-2xl font-bold">Interest and fees by month</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <MonthBars
              title={`Interest and fees by month, ${monthLong(d.months[0])} to ${monthLong(d.months[d.months.length - 1])}`}
              data={d.months.map((m, i) => ({
                key: m,
                label: monthShort(m),
                value: totals[i],
                selected: true,
                tooltip: (
                  <>
                    <strong>{monthLong(m)}</strong>
                    <span className="num block">{money(totals[i])}</span>
                  </>
                ),
              }))}
            />
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-muted">The numbers</summary>
              <table className="mt-2 w-full">
                <caption className="sr-only">Interest and fees by month</caption>
                <tbody className="divide-y divide-line">
                  {d.months.map((m, i) => (
                    <tr key={m}>
                      <th scope="row" className="py-1 text-left font-normal">
                        {monthLong(m)}
                      </th>
                      <td className="num py-1 text-right">{money(totals[i])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>
          <p className="mt-6 text-sm text-muted">
            Months from the Cash Flow sheet count under “Cash Flow sheet”; the sheet has no accounts. Balances
            are the latest approved statement’s, as printed.
          </p>
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

function AccountDetail({ d, name }: { d: Debt; name: string }) {
  const a = d.accounts.find((x) => x.name === name)!;
  const months = d.months.filter((m) => a.by_month[m]);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <h3 className="font-semibold">{d.year} by kind</h3>
        <ul className="mt-1 divide-y divide-line" aria-label={`${name}: ${d.year} by kind`}>
          {Object.entries(a.by_category).map(([k, v]) => (
            <li key={k} className="flex justify-between py-1">
              <span>{k}</span>
              <span className="num">{money(v)}</span>
            </li>
          ))}
          {Object.keys(a.by_category).length === 0 && <li className="py-1 text-muted">None this year.</li>}
        </ul>
      </div>
      <div>
        <h3 className="font-semibold">By month</h3>
        <ul className="mt-1 divide-y divide-line" aria-label={`${name}: by month`}>
          {months.map((m) => (
            <li key={m} className="flex justify-between py-1">
              <span>{monthLong(m)}</span>
              <span className="num">{money(a.by_month[m])}</span>
            </li>
          ))}
          {months.length === 0 && <li className="py-1 text-muted">None in the last 12 months.</li>}
        </ul>
      </div>
    </div>
  );
}
