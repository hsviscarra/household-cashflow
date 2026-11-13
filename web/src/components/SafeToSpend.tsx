import type { SafeToSpend as Safe } from "../api";
import { money, num } from "../money";

// Safe to spend (ADR-097, plan item C6): what is left for the rest of the month once the bills
// still due and the goals' plan are taken out. One number, and how it was reached.

const minus = (v: string | number) => (num(v) < 0 ? `−${money(Math.abs(num(v)))}` : money(v));

/** "1,350.00 until the end of the month, about 112.50 a day for 12 days." */
export function safeLine(s: Safe): string {
  const days = `${s.days_left} ${s.days_left === 1 ? "day" : "days"}`;
  if (num(s.amount) <= 0)
    return `Nothing: the bills still due and your goals take ${money(Math.abs(num(s.amount)))} more than what is left.`;
  return `${money(s.amount)} until the end of the month, about ${money(s.a_day)} a day for ${days}.`;
}

export default function SafeToSpend({ safe }: { safe: Safe }) {
  const over = num(safe.amount) <= 0;
  return (
    <div>
      <p
        className={`num mt-1 font-display text-3xl font-bold ${over ? "text-attention-ink" : ""}`}
        aria-label="Safe to spend"
      >
        {minus(safe.amount)}
      </p>
      <p className="mt-1 text-sm text-muted">{safeLine(safe)}</p>
      <dl className="mt-3 divide-y divide-line text-sm">
        <Line label="Money in, less spent and set aside, so far" value={minus(safe.left_so_far)} />
        <Line label="Income still to come this month" value={`+${money(safe.income_to_come)}`} />
        <Line label="Bills still due this month" value={`−${money(safe.bills_to_come)}`} />
        <Line label="Still to set aside for your goals" value={`−${money(safe.goals_to_go)}`} />
      </dl>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 py-1.5">
      <dt>{label}</dt>
      <dd className="num">{value}</dd>
    </div>
  );
}
