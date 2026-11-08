import KpiCard from "../components/KpiCard";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  fetchCategoryMonths,
  fetchMonthly,
  fetchPlan,
  type CashView,
  type CategoryMonth,
  type MonthlyCashflow,
} from "../api";
import { ExportLinks } from "../components/ExportLinks";
import LinesPanel, { type LinesTarget } from "../components/LinesPanel";
import { InOutColumns, Legend, TrendLine, type ColumnDatum } from "../components/charts";
import { money, monthLong, monthShort, num, parts, pct, signed } from "../money";

const outflows = (m: MonthlyCashflow) =>
  num(m.expenses) + num(m.card_payments) + num(m.savings) + num(m.debt_payments);

const VIEWS: { id: CashView; label: string; help: string }[] = [
  {
    id: "spending",
    label: "Spending view",
    help: "Card purchases count when you make them; paying the card is a transfer and doesn’t count again.",
  },
  {
    id: "cash",
    label: "Cash view",
    help: "Only money in and out of the bank accounts: a card counts when you pay it, as a card payment.",
  },
];

/** The year-by-year history (the former Overview), shown under the month on Cash flow. */
export default function Overview() {
  const [params, setParams] = useSearchParams();
  const view: CashView = params.get("view") === "cash" ? "cash" : "spending";
  const monthly = useQuery({ queryKey: ["cashflow", "monthly", view], queryFn: () => fetchMonthly(view) });
  const plan = useQuery({ queryKey: ["cashflow", "plan"], queryFn: fetchPlan });
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setParams(next);
  };

  const years = useMemo(
    () => [...new Set((monthly.data ?? []).map((m) => parts(m.cash_month).year))].sort(),
    [monthly.data],
  );
  const asked = Number(params.get("year"));
  const year = years.includes(asked) ? asked : years[years.length - 1];

  if (monthly.error)
    return (
      <p className="rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
        Could not load the cash flow: {(monthly.error as Error).message}. Check that the database is connected
        and reload the page.
      </p>
    );
  if (!monthly.data) return <p className="text-muted">Loading the cash flow…</p>;
  if (!monthly.data.length) return <EmptyOverview />;

  const inYear = monthly.data.filter((m) => parts(m.cash_month).year === year);
  const income = inYear.reduce((s, m) => s + num(m.income), 0);
  const out = inYear.reduce((s, m) => s + outflows(m), 0);
  const net = income - out;
  const expenses = inYear.reduce((s, m) => s + num(m.expenses), 0);
  const saved = inYear.reduce((s, m) => s + num(m.savings), 0);
  const debt = inYear.reduce((s, m) => s + num(m.debt_payments), 0);
  const cards = inYear.reduce((s, m) => s + num(m.card_payments), 0);
  // Plan months only where no actual month exists yet (statements replace the plan).
  const actualMonths = new Set(inYear.map((m) => m.cash_month));
  const planInYear = (plan.data ?? []).filter(
    (p) => parts(p.month).year === year && !actualMonths.has(p.month),
  );
  const first = inYear[0].cash_month;
  const last = inYear[inYear.length - 1].cash_month;
  const span =
    inYear.length === 12
      ? String(year)
      : first === last
        ? monthLong(first)
        : `${monthShort(first)}–${monthShort(last)} ${year}`;

  const columns: ColumnDatum[] = (
    [
      ...inYear.map((m) => ({
        key: m.cash_month,
        label: monthShort(m.cash_month),
        in: num(m.income),
        out: outflows(m),
        tooltip: <MonthTip title={monthLong(m.cash_month)} income={num(m.income)} out={outflows(m)} />,
      })),
      ...planInYear.map((p) => ({
        key: p.month,
        label: monthShort(p.month),
        in: num(p.income),
        out: num(p.outflows),
        plan: true,
        tooltip: (
          <MonthTip title={`${monthLong(p.month)} (plan)`} income={num(p.income)} out={num(p.outflows)} />
        ),
      })),
    ] as ColumnDatum[]
  ).sort((a, b) => a.key.localeCompare(b.key));

  return (
    <section>
      <h2 className="font-display text-3xl font-bold leading-tight">
        {net >= 0 ? (
          <>
            In {span} you kept <span className="num">{money(net)}</span> of{" "}
            <span className="num">{money(income)}</span>.
          </>
        ) : (
          <>
            In {span} you spent <span className="num">{money(-net)}</span> more than came in.
          </>
        )}
      </h2>
      <p className="mt-2 text-muted">
        The whole history, year by year, for both of you. Money in and out of the household by month: the Cash
        Flow workbook through June 2026, then approved statements. A month is complete once every account’s
        statement for it is loaded.
      </p>

      <div role="group" aria-label="View" className="mt-6 flex flex-wrap gap-2">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            aria-pressed={v.id === view}
            className={`btn ${v.id === view ? "bg-ink text-ground" : "btn-secondary"}`}
            onClick={() => setParam("view", v.id === "spending" ? null : v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
      <div className="mt-2">
        <ExportLinks
          dataset={view === "cash" ? "monthly_cash" : "monthly_cashflow"}
          label={`every month (${view === "cash" ? "cash" : "spending"} view)`}
        />
      </div>
      <p className="mt-2 text-sm text-muted">{VIEWS.find((v) => v.id === view)?.help}</p>

      <div role="group" aria-label="Year" className="mt-4 flex gap-2 overflow-x-auto pb-1">
        {years.map((y) => (
          <button
            key={y}
            aria-pressed={y === year}
            className={`btn ${y === year ? "bg-ink text-ground" : "btn-secondary"}`}
            onClick={() => setParam("year", String(y))}
          >
            {y}
          </button>
        ))}
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard label="Money in" value={money(income)} />
        <KpiCard label="Money out" value={money(out)} />
        <KpiCard label="Kept" value={signed(net)} tone={net < 0 ? "bad" : undefined} />
        <KpiCard label="Share kept" value={pct(income ? net / income : null)} />
      </dl>
      <p className="mt-3 text-sm text-muted">
        Money out = spending <span className="num">{money(expenses)}</span>
        {view === "cash" && (
          <>
            {" "}
            + card payments <span className="num">{money(cards)}</span>
          </>
        )}{" "}
        + savings and investing <span className="num">{money(saved)}</span> + loan payments{" "}
        <span className="num">{money(debt)}</span>.
      </p>

      <div className="mt-8 rounded-2xl bg-surface p-4 md:p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="font-display text-2xl font-bold">Money in and out, {year}</h2>
          <Legend
            items={[
              { label: "Money in", color: "var(--color-flow-in)" },
              { label: "Money out", color: "var(--color-flow-out)" },
              ...(planInYear.length ? [{ label: "Plan", color: "var(--color-muted)", faded: true }] : []),
            ]}
          />
        </div>
        <div className="mt-4 overflow-hidden">
          <InOutColumns data={columns} title={`Money in and out by month, ${year}`} />
        </div>
      </div>

      <div className="mt-6 rounded-2xl bg-surface p-4 md:p-6">
        <h2 className="font-display text-2xl font-bold">Kept over time</h2>
        <p className="text-sm text-muted">
          Running total of money in minus money out since {monthLong(monthly.data[0].cash_month)} (the
          workbook’s “Disposable income Total”).
        </p>
        <div className="mt-4 overflow-hidden">
          <TrendLine
            title="Cumulative kept by month"
            data={monthly.data.map((m) => ({
              key: m.cash_month,
              value: num(m.cumulative_net),
              tick: parts(m.cash_month).month === 1 ? String(parts(m.cash_month).year) : undefined,
              tooltip: (
                <>
                  <div className="font-semibold">{monthLong(m.cash_month)}</div>
                  <div className="num">Total {signed(m.cumulative_net)}</div>
                  <div className="num text-muted">Month {signed(m.net)}</div>
                </>
              ),
            }))}
          />
        </div>
      </div>

      <CategoryTable year={year} months={inYear.map((m) => m.cash_month)} />
    </section>
  );
}

function MonthTip({ title, income, out }: { title: string; income: number; out: number }) {
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

const TYPE_ORDER = ["income", "expense", "fee_interest", "refund", "savings", "debt_payment"];
const TYPE_LABEL: Record<string, string> = {
  income: "Money in",
  expense: "Spending",
  fee_interest: "Spending",
  refund: "Spending",
  savings: "Savings and investing",
  debt_payment: "Card and loan payments",
};

type Row = {
  key: string;
  name: string;
  color: string | null;
  byMonth: Map<string, number>;
  total: number;
  type: string;
  id: number;
  detail: boolean;
};

function CategoryTable({ year, months }: { year: number; months: string[] }) {
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

function EmptyOverview() {
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
