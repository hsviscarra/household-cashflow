import { money, signed, num, monthShort } from "../../money";
import { useQuery } from "@tanstack/react-query";
import { fetchCategoryMonths, type CategoryMonth, fetchReconcile } from "../../api";
import { useState } from "react";
import LinesPanel, { type LinesTarget } from "../../components/LinesPanel";
import { Link } from "react-router-dom";

export function MonthTip({ title, income, out }: { title: string; income: number; out: number }) {
  return (
    <>
      <div className="font-semibold">{title}</div>
      <div className="num flex justify-between gap-2">
        <span>In</span>
        <span>{money(income)}</span>
      </div>
      <div className="num flex justify-between gap-2">
        <span>Out</span>
        <span>{money(out)}</span>
      </div>
      <div className="num flex justify-between gap-2 font-semibold">
        <span>Kept</span>
        <span>{signed(income - out)}</span>
      </div>
    </>
  );
}

export const TYPE_ORDER = ["income", "expense", "fee_interest", "refund", "savings", "debt_payment"];

export const TYPE_LABEL: Record<string, string> = {
  income: "Money in",
  expense: "Spending",
  fee_interest: "Spending",
  refund: "Spending",
  savings: "Savings and investing",
  debt_payment: "Card and loan payments",
};

export type Row = {
  key: string;
  name: string;
  color: string | null;
  byMonth: Map<string, number>;
  total: number;
  type: string;
  id: number;
  detail: boolean;
};

export function CategoryTable({ year, months }: { year: number; months: string[] }) {
  const { data } = useQuery({
    queryKey: ["cashflow", "categories", year],
    queryFn: () => fetchCategoryMonths(year),
  });
  const [target, setTarget] = useState<LinesTarget | null>(null);
  if (!data) return null;

  const sections = new Map<string, Map<string, Row>>();
  for (const c of data as CategoryMonth[]) {
    const section = TYPE_LABEL[c.type] ?? c.type;
    const rows = sections.get(section) ?? new Map<string, Row>();
    sections.set(section, rows);
    // Savings and payments read better by what they are (Investing, Card Payment, Loan Payments).
    const detail = c.type === "savings" || c.type === "debt_payment";
    const key = detail ? `c${c.category_id}` : `g${c.group_id}`;
    const row = rows.get(key) ?? {
      key,
      name: detail ? c.category_name : c.group_name,
      color: c.group_color,
      byMonth: new Map(),
      total: 0,
      type: c.type,
      id: detail ? c.category_id : c.group_id,
      detail,
    };
    row.byMonth.set(c.cash_month, (row.byMonth.get(c.cash_month) ?? 0) + num(c.amount));
    row.total += num(c.amount);
    rows.set(key, row);
  }
  const order = [...new Set(TYPE_ORDER.map((t) => TYPE_LABEL[t]))].filter((s) => sections.has(s));

  return (
    <div className="mt-6">
      <h2 className="font-display text-2xl font-bold">By category, {year}</h2>
      <p className="text-sm text-muted">Click any amount to see its lines and fix them.</p>
      {target && <LinesPanel target={target} onClose={() => setTarget(null)} />}
      <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-max text-sm">
          <thead className="bg-surface text-muted">
            <tr>
              <th scope="col" className="sticky left-0 bg-surface px-4 py-3 text-left font-semibold">
                Category
              </th>
              {months.map((m) => (
                <th key={m} scope="col" className="px-3 py-3 text-right font-semibold">
                  {monthShort(m)}
                </th>
              ))}
              <th scope="col" className="px-4 py-3 text-right font-semibold">
                Total
              </th>
            </tr>
          </thead>
          {order.map((section) => {
            const rows = [...sections.get(section)!.values()].sort((a, b) => b.total - a.total);
            return (
              <tbody key={section} className="divide-y divide-line">
                <tr className="bg-ground">
                  <th
                    colSpan={months.length + 2}
                    scope="colgroup"
                    className="px-4 pb-1 pt-4 text-left font-display text-base font-bold"
                  >
                    {section}
                  </th>
                </tr>
                {rows.map((r) => (
                  <tr key={r.key}>
                    <th scope="row" className="sticky left-0 bg-ground px-4 py-2 text-left font-normal">
                      <span className="flex items-center gap-2">
                        <span
                          aria-hidden
                          className="inline-block h-3 w-3 shrink-0 rounded-full"
                          style={{ background: r.color ?? "var(--color-muted)" }}
                        />
                        {r.name}
                      </span>
                    </th>
                    {months.map((m) => (
                      <td key={m} className="num px-3 py-2 text-right">
                        {r.byMonth.has(m) ? (
                          <button
                            type="button"
                            className="num underline decoration-line-strong decoration-dotted underline-offset-4 hover:text-primary"
                            aria-label={`${r.name}, ${monthShort(m)}: ${money(r.byMonth.get(m)!)}. See the lines`}
                            onClick={() =>
                              setTarget({
                                title: r.name,
                                month: m,
                                filter: r.detail
                                  ? { category_id: r.id, type: r.type }
                                  : { group_id: r.id, type: r.type },
                                moveTo: r.detail ? r.id : null,
                              })
                            }
                          >
                            {money(r.byMonth.get(m)!)}
                          </button>
                        ) : (
                          ""
                        )}
                      </td>
                    ))}
                    <td className="num px-4 py-2 text-right font-semibold">{money(r.total)}</td>
                  </tr>
                ))}
              </tbody>
            );
          })}
        </table>
      </div>
    </div>
  );
}

/** Kept vs what the balances did, and what explains the gap (ADR-051). */
export function WhereMoney({ from, to }: { from: string; to: string }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["cashflow", "reconcile", from, to],
    queryFn: () => fetchReconcile(from, to),
  });
  const r = q.data;
  if (!r?.accounts) return null;
  const gap = num(r.gap);
  const ok = Math.abs(gap) < 50;
  return (
    <section aria-label="Where's the money" className="card mt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-xl font-bold">Where’s the money?</h2>
        <button
          className="text-sm font-semibold text-primary"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? "Hide the accounts" : "See the accounts"}
        </button>
      </div>
      <p className="mt-2">
        You kept <span className="num font-semibold">{signed(num(r.kept))}</span> from {monthShort(r.start)}{" "}
        to {monthShort(r.end)}; your bank and card balances changed by{" "}
        <span className="num font-semibold">{signed(num(r.balances_change))}</span>.{" "}
        {ok ? (
          <span className="text-good-ink">They agree.</span>
        ) : (
          <span className="text-attention-ink">
            <span className="num font-semibold">{signed(gap)}</span> isn’t explained yet.
          </span>
        )}
      </p>
      {r.workbook_months > 0 && (
        <p className="mt-1 text-sm text-muted">
          {r.workbook_months} of these months come from the Cash Flow workbook, which has no balances to
          compare.
        </p>
      )}
      {!ok && r.causes.length > 0 && (
        <ul className="mt-3 space-y-2">
          {r.causes.map((c) => (
            <li key={c.key} className="rounded-xl bg-surface px-4 py-3 text-sm">
              <Link to={c.link} className="font-semibold text-primary underline">
                {c.title}
              </Link>
              {num(c.amount) !== 0 && <span className="num ml-2 font-semibold">{money(c.amount)}</span>}
              <span className="block text-muted">{c.detail}</span>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-1 text-left font-semibold">Account</th>
                <th className="py-1 text-right font-semibold">Start</th>
                <th className="py-1 text-right font-semibold">End</th>
                <th className="py-1 text-right font-semibold">Adds</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {r.accounts.map((a) => (
                <tr key={a.account_id}>
                  <td className="py-1.5">
                    {a.name}
                    {a.kind === "card" && <span className="text-muted"> · owed</span>}
                  </td>
                  <td className="num py-1.5 text-right">
                    {a.start !== null ? money(a.start) : "—"}
                    {a.start_on && <span className="block text-xs text-muted">{monthShort(a.start_on)}</span>}
                  </td>
                  <td className="num py-1.5 text-right">
                    {a.end !== null ? money(a.end) : "—"}
                    {a.end_on && <span className="block text-xs text-muted">{monthShort(a.end_on)}</span>}
                  </td>
                  <td className="num py-1.5 text-right font-semibold">
                    {a.change !== null ? signed(num(a.change)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function EmptyOverview() {
  return (
    <section className="max-w-3xl">
      <h2 className="font-display text-3xl font-bold leading-tight">No cash flow yet</h2>
      <p className="mt-3 text-lg text-muted">
        Load the Cash Flow workbook to see every month since August 2019. Statements add the detail from F4
        on.
      </p>
      <Link to="/import" className="btn btn-primary mt-6">
        Load the Excel history
      </Link>
    </section>
  );
}
