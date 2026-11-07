// The monthly budget per group (ADR-039): what's budgeted, spent and left, a pace mark for today,
// rollover from earlier months, and the 3-month average to start from.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { fetchBudget, setBudget, startBudgetFromAverage, type GroupBudget, type MonthBudget } from "../api";
import KpiCard from "../components/KpiCard";
import { addMonths, localToday, money, monthLong, num } from "../money";

const STATUS: Record<GroupBudget["status"], { text: string; cls: string }> = {
  over: { text: "Over", cls: "bg-danger-bg text-danger-ink" },
  ahead: { text: "Ahead of pace", cls: "bg-attention-bg text-attention-ink" },
  on_track: { text: "On track", cls: "bg-good-bg text-good-ink" },
  none: { text: "No budget", cls: "bg-surface text-muted" },
};

/** "$110.00 left · $86.67 by today" or "$40.00 over" */
export function leftWords(g: GroupBudget, dayShare: number): string {
  if (g.budget === null) return `${money(g.spent)} spent`;
  const left = num(g.left);
  if (left < 0) return `${money(-left)} over`;
  return dayShare > 0 && dayShare < 1
    ? `${money(left)} left · ${money(g.expected)} by today`
    : `${money(left)} left`;
}

export default function BudgetPage() {
  const [params, setParams] = useSearchParams();
  const thisMonth = localToday().slice(0, 7);
  const raw = params.get("month");
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? raw : thisMonth;
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["budget", month], queryFn: () => fetchBudget(month) });
  const start = useMutation({
    mutationFn: () => startBudgetFromAverage(month),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budget"] }),
  });
  const go = (by: number) => setParams({ month: addMonths(`${month}-01`, by).slice(0, 7) });
  const b = q.data;
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">
            Budget, {monthLong(`${month}-01`)}
          </h1>
          <p className="mt-2 max-w-3xl text-lg text-muted">
            A monthly amount per spending group. With rollover, what's left (or overspent) carries into the
            next month.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => go(-1)}
            aria-label="Previous month"
          >
            ←
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => go(1)} aria-label="Next month">
            →
          </button>
        </div>
      </div>
      {q.error && <p className="mt-4 text-danger-ink">{(q.error as Error).message}</p>}
      {b && (
        <>
          <dl className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Budgeted" value={money(b.budgeted)} />
            <KpiCard label="Spent in budgeted groups" value={money(b.spent)} />
            <KpiCard
              label={num(b.left) < 0 ? "Over" : "Left"}
              value={money(Math.abs(num(b.left)))}
              tone={num(b.left) < 0 ? "bad" : undefined}
            />
            <KpiCard
              label="Outside any budget"
              value={money(b.unbudgeted)}
              note={num(b.unbudgeted) > 0 ? "Groups without a budget" : undefined}
            />
          </dl>
          {!b.groups.some((g) => g.budget !== null) && (
            <div className="card mt-6">
              <p className="font-semibold">No budget for {monthLong(`${month}-01`)} yet.</p>
              <p className="mt-1 text-sm text-muted">
                Start every group at its average of the last 3 months (rounded up to $10), then adjust.
              </p>
              <button
                type="button"
                className="btn btn-primary mt-3"
                disabled={start.isPending}
                onClick={() => start.mutate()}
              >
                Start from the 3-month average
              </button>
            </div>
          )}
          <ul className="mt-6 space-y-3" aria-label="Groups">
            {b.groups.map((g) => (
              <GroupRow key={g.group_id} g={g} b={b} month={month} />
            ))}
          </ul>
          {b.groups.length === 0 && <p className="mt-6 text-muted">No spending this month yet.</p>}
        </>
      )}
    </section>
  );
}

function GroupRow({ g, b, month }: { g: GroupBudget; b: MonthBudget; month: string }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(g.budget ?? g.suggested ?? "");
  const [rollover, setRollover] = useState(g.rollover);
  const save = useMutation({
    mutationFn: () => setBudget(g.group_id, `${month}-01`, String(Math.max(0, num(amount))), rollover),
    onSuccess: () => {
      setEditing(false);
      void qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });
  const share = num(b.day_share);
  const avail = num(g.available);
  const width = avail > 0 ? Math.min(100, (num(g.spent) / avail) * 100) : num(g.spent) > 0 ? 100 : 0;
  const s = STATUS[g.status];
  const barColor = g.status === "over" ? "bg-danger-ink" : g.status === "ahead" ? "bg-warn" : "bg-primary";
  return (
    <li>
      <section className="card" aria-label={g.name}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className="h-3 w-3 rounded-full"
              style={{ background: g.color ?? "var(--color-muted)" }}
            />
            <Link className="font-display text-lg font-bold hover:underline" to={`/spending?month=${month}`}>
              {g.name}
            </Link>
            <span className={`pill ${s.cls}`}>{s.text}</span>
            {g.rollover && <span className="pill pill-muted">Rollover</span>}
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="num">
              <strong>{money(g.spent)}</strong>
              {g.budget !== null && <span className="text-muted"> of {money(g.available)}</span>}
            </span>
            <button type="button" className="btn btn-quiet h-9 px-3" onClick={() => setEditing(!editing)}>
              {g.budget === null ? "Set a budget" : "Change"}
            </button>
          </div>
        </div>
        {g.budget !== null && (
          <div
            className="relative mt-3 h-2.5 rounded-full bg-surface"
            role="img"
            aria-label={`${Math.round(width)}% of the budget spent`}
          >
            <span className={`block h-full rounded-full ${barColor}`} style={{ width: `${width}%` }} />
            {share > 0 && share < 1 && (
              <span
                aria-hidden
                className="absolute -top-1 h-4.5 w-0.5 bg-ink"
                style={{ left: `${share * 100}%` }}
                title="Today"
              />
            )}
          </div>
        )}
        <p className="mt-2 text-sm text-muted">
          {leftWords(g, share)}
          {num(g.carried) !== 0 &&
            ` · ${num(g.carried) > 0 ? "+" : "−"}${money(Math.abs(num(g.carried)))} from earlier months`}
          {g.budget === null && g.suggested && ` · average ${money(g.suggested)} a month`}
        </p>
        {editing && (
          <form
            className="mt-3 flex flex-wrap items-end gap-3 border-t border-line pt-3"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <label>
              <span className="label">Each month from {monthLong(`${month}-01`)}</span>
              <input
                className="field num w-36"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
            <label className="flex h-11 items-center gap-2 text-sm">
              <input type="checkbox" checked={rollover} onChange={(e) => setRollover(e.target.checked)} />
              Roll what's left into next month
            </label>
            <button type="submit" className="btn btn-primary" disabled={save.isPending}>
              Save
            </button>
            {g.suggested && (
              <button type="button" className="btn btn-quiet" onClick={() => setAmount(g.suggested!)}>
                Use the average ({money(g.suggested)})
              </button>
            )}
            <p className="w-full text-xs text-muted">0 removes the budget from this month on.</p>
            {save.error && <p className="w-full text-sm text-danger-ink">{(save.error as Error).message}</p>}
          </form>
        )}
      </section>
    </li>
  );
}
