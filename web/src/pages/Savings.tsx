import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { fetchSavings, setDebtTerms, type DebtLine, type PayoffPlan, type Savings } from "../api";
import { StackedColumns } from "../components/charts";
import SafeToSpend from "../components/SafeToSpend";
import { addMonths, money, monthLong, monthShort, num, pct } from "../money";
import { useSettings } from "../prefs";

// Saving, on one page (ADR-097, plan item C5): the savings rate by month, what the goals need,
// and the debts with the order to pay them in. Calculations from your own numbers.

const RATE_FROM: Record<string, string> = {
  typed: "typed",
  table: "estimated from its table",
};
const MINIMUM_FROM: Record<string, string> = {
  typed: "typed",
  table: "its next installment",
  payment: "its monthly payment",
  assumed: "assumed: 3% of the balance",
};
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

/** "14 months (January 2028)": how long from the month of `today`. */
export function howLong(months: number | null, today: string): string {
  if (months == null) return "never, at these payments";
  if (months === 0) return "nothing to pay";
  return `${months} ${months === 1 ? "month" : "months"} (${monthLong(addMonths(`${today.slice(0, 7)}-01`, months - 1))})`;
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
      <h2 id="rate" className="font-display text-xl font-bold">
        Savings rate by month
      </h2>
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

function Debts({ s, extra, setExtra }: { s: Savings; extra: number; setExtra: (v: number) => void }) {
  const [typed, setTyped] = useState(extra ? String(extra) : "");
  const [editing, setEditing] = useState<string | null>(null);
  const names = new Map(s.debts.map((d) => [d.key, d.name]));
  const p = s.payoff;
  const left = s.debts.filter((d) => !d.planned && d.kind !== "card");
  const cards = s.debts.filter((d) => !d.planned && d.kind === "card");
  return (
    <section className="card" aria-labelledby="debts">
      <h2 id="debts" className="font-display text-xl font-bold">
        Debts: which to pay first
      </h2>
      {s.debts.length === 0 ? (
        <p className="mt-2 text-muted">Nothing is owed on the balance sheet.</p>
      ) : (
        <>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">What is owed</caption>
              <thead className="text-muted">
                <tr>
                  {["Debt", "Owed", "Rate a year", "Paid a month", "Interest and fees, 12 months", ""].map(
                    (h, i) => (
                      <th
                        key={h || "edit"}
                        scope="col"
                        className={`py-1 font-semibold ${i && i < 5 ? "text-right" : "text-left"}`}
                      >
                        {h || <span className="sr-only">Edit</span>}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {s.debts.map((d) =>
                  editing === d.key ? (
                    <TermsRow key={d.key} d={d} done={() => setEditing(null)} />
                  ) : (
                    <tr key={d.key}>
                      <th scope="row" className="py-1.5 text-left font-medium">
                        {d.name}
                      </th>
                      <td className="num py-1.5 text-right">{money(d.balance)}</td>
                      <td className="py-1.5 text-right">
                        {d.rate != null ? (
                          <>
                            <span className="num">{(num(d.rate) * 100).toFixed(1)}%</span>
                            <span className="block text-xs text-muted">{RATE_FROM[d.rate_from ?? ""]}</span>
                          </>
                        ) : d.kind === "card" ? (
                          <span className="text-muted">type it if you carry a balance</span>
                        ) : (
                          <span className="text-attention-ink">not known</span>
                        )}
                      </td>
                      <td className="py-1.5 text-right">
                        {d.minimum != null ? (
                          <>
                            <span className="num">{money(d.minimum)}</span>
                            <span className="block text-xs text-muted">
                              {MINIMUM_FROM[d.minimum_from ?? ""]}
                            </span>
                          </>
                        ) : d.kind === "card" ? (
                          "—"
                        ) : (
                          <span className="text-attention-ink">not known</span>
                        )}
                      </td>
                      <td className="num py-1.5 text-right">
                        {num(d.interest_12) > 0 ? money(d.interest_12) : "—"}
                      </td>
                      <td className="py-1.5 pl-3 text-right">
                        <button
                          className="text-primary underline"
                          aria-label={`Edit ${d.name}`}
                          onClick={() => setEditing(d.key)}
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          {left.length > 0 && (
            <p className="mt-2 text-sm text-muted">
              Not in the comparison until its rate and monthly payment are known:{" "}
              {left.map((d) => d.name).join(", ")}.
            </p>
          )}
          {cards.length > 0 && (
            <p className="mt-2 text-sm text-muted">
              Cards are left out: a card’s balance is this month’s purchases unless you carry it. Type a
              card’s rate (Edit) to plan it as a debt.
            </p>
          )}
          <form
            className="mt-4 flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setExtra(Math.max(0, Number(typed) || 0));
            }}
          >
            <label>
              <span className="label">Extra toward debts each month</span>
              <input
                className="field num !w-40"
                inputMode="decimal"
                placeholder="0.00"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            </label>
            <button type="submit" className="btn btn-secondary">
              Compare
            </button>
          </form>
          {p && (
            <>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Payoff orders compared</caption>
                  <thead className="text-muted">
                    <tr>
                      {["", "Debt-free in", "Interest paid", "Paid off in this order"].map((h, i) => (
                        <th
                          key={h || "plan"}
                          scope="col"
                          className={`py-1 font-semibold ${i === 2 ? "text-right" : "text-left"} ${i === 3 ? "pl-4" : ""}`}
                        >
                          {h || <span className="sr-only">Plan</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    <PlanRow
                      label="Minimums only, nothing extra"
                      plan={p.minimums}
                      names={names}
                      today={s.today}
                    />
                    <PlanRow label="Highest rate first" plan={p.avalanche} names={names} today={s.today} />
                    <PlanRow label="Smallest balance first" plan={p.snowball} names={names} today={s.today} />
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-sm" aria-label="Payoff summary">
                {payoffLine(p, num(p.extra))}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}

/** What the comparison says, in one sentence. */
export function payoffLine(p: NonNullable<Savings["payoff"]>, extra: number): string {
  const budget = `With the monthly payments${extra > 0 ? ` plus ${money(extra)}` : ""}, and each paid-off debt's payment moved to the next`;
  const versus = num(p.minimums.interest) - num(p.avalanche.interest);
  const saved = num(p.saved);
  const first =
    p.avalanche.months == null
      ? `${budget}, the debts are never paid off: the payments don't cover the interest.`
      : `${budget}, highest rate first costs ${money(Math.max(0, versus))} less interest than paying only the minimums.`;
  const second =
    saved < 0.005
      ? " Both orders cost the same here."
      : num(p.avalanche.interest) <= num(p.snowball.interest)
        ? ` Highest rate first costs ${money(saved)} less than smallest balance first.`
        : ` Smallest balance first costs ${money(saved)} less than highest rate first.`;
  return first + (p.avalanche.months == null ? "" : second);
}

function PlanRow({
  label,
  plan,
  names,
  today,
}: {
  label: string;
  plan: PayoffPlan;
  names: Map<string, string>;
  today: string;
}) {
  return (
    <tr>
      <th scope="row" className="py-1.5 pr-3 text-left font-medium">
        {label}
      </th>
      <td className="py-1.5">{howLong(plan.months, today)}</td>
      <td className="num py-1.5 text-right">{money(plan.interest)}</td>
      <td className="py-1.5 pl-4 text-muted">
        {plan.order.map((k) => `${names.get(k) ?? k} (${plan.paid_in[k]})`).join(" → ") || "—"}
      </td>
    </tr>
  );
}

/** Type a debt's yearly rate (as a percent) and its monthly payment; empty forgets it. */
function TermsRow({ d, done }: { d: DebtLine; done: () => void }) {
  const qc = useQueryClient();
  const [rate, setRate] = useState(d.rate != null ? String(Number((num(d.rate) * 100).toFixed(2))) : "");
  const [minimum, setMinimum] = useState(d.minimum != null ? String(num(d.minimum)) : "");
  const save = useMutation({
    mutationFn: () =>
      setDebtTerms(d.key, {
        rate: rate.trim() ? (Number(rate) / 100).toFixed(4) : null,
        minimum: minimum.trim() ? Number(minimum).toFixed(2) : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savings"] });
      done();
    },
  });
  return (
    <tr className="bg-surface">
      <th scope="row" className="py-2 text-left font-medium">
        {d.name}
      </th>
      <td colSpan={5} className="py-2">
        <form
          className="flex flex-wrap items-end justify-end gap-2"
          aria-label={`Terms of ${d.name}`}
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <label>
            <span className="label">Rate a year, %</span>
            <input
              className="field num !w-28"
              inputMode="decimal"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
            />
          </label>
          <label>
            <span className="label">Paid a month</span>
            <input
              className="field num !w-32"
              inputMode="decimal"
              value={minimum}
              onChange={(e) => setMinimum(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary h-10 px-4" disabled={save.isPending}>
            Save
          </button>
          <button type="button" className="btn btn-quiet h-10 px-3" onClick={done}>
            Cancel
          </button>
          {save.error && (
            <span role="alert" className="w-full text-right text-danger-ink">
              {(save.error as Error).message}
            </span>
          )}
        </form>
      </td>
    </tr>
  );
}
