import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchSavings, type Savings } from "../api";
import ChartTools from "../components/ChartTools";
import { StackedColumns } from "../components/charts";
import SafeToSpend from "../components/SafeToSpend";
import { money, monthLong, monthShort, num, pct } from "../money";
import { useSettings } from "../prefs";
import Debts, { howLong, payoffLine } from "./savings/Debts";

export { howLong, payoffLine };

// Saving, on one page (ADR-097, plan item C5): the savings rate by month, what the goals need,
// and the debts with the order to pay them in. Calculations from your own numbers.

const GOAL_STATUS: Record<string, string> = {
  on_pace: "On pace",
  behind: "Behind",
  late: "Past its date",
  open: "No date",
};

/** "You kept 34% of what came in over the last 11 months." */
export function rateHeadline(s: Savings): string {
  const whole = s.months.filter((m) => !m.running && num(m.money_in) > 0).length;
  if (s.rate_12 == null || !whole) return "Saving";
  return `You kept ${pct(s.rate_12)} of what came in over the last ${whole} ${whole === 1 ? "month" : "months"}`;
}

export default function SavingsPage() {
  const { settings, set } = useSettings();
  const extra = Math.max(0, Number(settings["savings:extra"]) || 0);
  const q = useQuery({
    queryKey: ["savings", extra],
    queryFn: () => fetchSavings(extra),
    placeholderData: (old) => old,
  });
  const s = q.data;
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">{s ? rateHeadline(s) : "Saving"}</h1>
      <p className="mt-2 max-w-3xl text-lg text-muted">
        How much of your income stays, what your goals need each month, and what your debts cost. Calculations
        from your own numbers; they don’t recommend an investment or a product.
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load this page: {(q.error as Error).message}
        </p>
      )}
      {!s && !q.error && <p className="mt-6 text-muted">Adding it up…</p>}
      {s && (
        <div className="mt-6 space-y-6">
          <section className="card" aria-labelledby="safe">
            <h2 id="safe" className="font-display text-xl font-bold">
              Safe to spend this month
            </h2>
            <SafeToSpend safe={s.safe} />
          </section>
          <Rate s={s} />
          <GoalNeeds s={s} />
          <Debts s={s} extra={extra} setExtra={(v) => set("savings:extra", v)} />
        </div>
      )}
    </section>
  );
}

function Rate({ s }: { s: Savings }) {
  const title = `Share of income kept, by month (%), ${monthLong(s.months[0]?.month ?? s.today)} to ${monthLong(s.today)}`;
  return (
    <section className="card" aria-labelledby="rate">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="rate" className="font-display text-xl font-bold">
          Savings rate by month
        </h2>
        <ChartTools
          name="Savings rate"
          csv={{
            file: "savings-rate.csv",
            rows: () => [
              ["Month", "Money in", "Spent", "Kept", "Rate", "Set aside"],
              ...s.months.map((m) => [
                m.month.slice(0, 7),
                m.money_in,
                m.spent,
                m.kept,
                m.rate ?? "",
                m.set_aside,
              ]),
            ],
          }}
          explain="Explain our savings rate over the last year: the best and worst months and what made them so."
        />
      </div>
      <p className="mt-1 text-sm text-muted">
        Kept is money in less what was spent: what was there to set aside or leave in the bank.
      </p>
      {s.months.length > 0 && (
        <div className="mt-3">
          <StackedColumns
            title={title}
            data={s.months.map((m) => ({
              key: m.month,
              label: monthShort(m.month),
              selected: m.running,
              segments: [
                {
                  key: "rate",
                  color: "var(--color-flow-in)",
                  value: Math.max(0, num(m.rate) * 100),
                },
              ],
              tooltip: (
                <>
                  <strong>{monthLong(m.month)}</strong>
                  {m.running && <span className="block text-muted">so far</span>}
                  <span className="num block">In {money(m.money_in)}</span>
                  <span className="num block">Spent {money(m.spent)}</span>
                  <span className="num block font-semibold">
                    Kept {money(m.kept)} · {pct(m.rate)}
                  </span>
                </>
              ),
            }))}
          />
        </div>
      )}
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-muted">The numbers</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Savings rate by month</caption>
            <thead className="text-muted">
              <tr>
                {["Month", "Money in", "Spent", "Kept", "Rate", "Set aside"].map((h, i) => (
                  <th key={h} scope="col" className={`py-1 font-semibold ${i ? "text-right" : "text-left"}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {s.months.map((m) => (
                <tr key={m.month}>
                  <th scope="row" className="py-1 text-left font-normal">
                    {monthLong(m.month)}
                    {m.running && <span className="text-muted"> (so far)</span>}
                  </th>
                  <td className="num py-1 text-right">{money(m.money_in)}</td>
                  <td className="num py-1 text-right">{money(m.spent)}</td>
                  <td className="num py-1 text-right">{money(m.kept)}</td>
                  <td className="num py-1 text-right font-semibold">{pct(m.rate)}</td>
                  <td className="num py-1 text-right text-muted">{money(m.set_aside)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function GoalNeeds({ s }: { s: Savings }) {
  const g = s.goals;
  return (
    <section className="card" aria-labelledby="needs">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="needs" className="font-display text-xl font-bold">
          What your goals need each month
        </h2>
        <Link to="/goals" className="text-sm font-semibold text-primary">
          Edit goals →
        </Link>
      </div>
      {g.goals.length === 0 ? (
        <p className="mt-2 text-muted">No goal is open. Add one on Goals to see what it needs a month.</p>
      ) : (
        <>
          <p className="mt-2" aria-label="Goals this month">
            To arrive on time your goals need <strong className="num">{money(g.needed)}</strong> a month; you
            plan <strong className="num">{money(g.planned)}</strong>
            {num(g.short) > 0 ? (
              <>
                , <span className="text-attention-ink">{money(g.short)} short</span>
              </>
            ) : (
              ", which covers it"
            )}
            . This month <strong className="num">{money(g.saved)}</strong> went into savings so far
            {num(g.to_go) > 0 ? `; ${money(g.to_go)} of the plan is still to go.` : ": the plan is covered."}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">What each goal needs a month</caption>
              <thead className="text-muted">
                <tr>
                  {["Goal", "By", "Still to save", "Needs a month", "Planned a month", ""].map((h, i) => (
                    <th
                      key={h || "status"}
                      scope="col"
                      className={`py-1 font-semibold ${i > 1 && i < 5 ? "text-right" : "text-left"} ${i === 5 ? "pl-4" : ""}`}
                    >
                      {h || <span className="sr-only">Status</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {g.goals.map((x) => (
                  <tr key={x.goal_id}>
                    <th scope="row" className="py-1.5 text-left font-medium">
                      {x.name}
                    </th>
                    <td className="py-1.5">{x.target_date ? monthLong(x.target_date) : "—"}</td>
                    <td className="num py-1.5 text-right">{money(x.left)}</td>
                    <td className="num py-1.5 text-right">
                      {x.needed_monthly != null ? money(x.needed_monthly) : "—"}
                    </td>
                    <td className="num py-1.5 text-right">
                      {x.monthly_amount != null ? money(x.monthly_amount) : "—"}
                    </td>
                    <td className="py-1.5 pl-4">
                      <span className={x.status === "on_pace" ? "text-good-ink" : "text-attention-ink"}>
                        {GOAL_STATUS[x.status] ?? x.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
