import { useQuery } from "@tanstack/react-query";
import {
  fetchStatus,
  type Flows,
  fetchProjection,
  fetchBalanceSheet,
  fetchPeople,
  fetchGoals,
  fetchReview,
} from "../../api";
import { Link } from "react-router-dom";
import { day, ALL, WIDGETS, Card, comingUp, COMING_DAYS } from "./shared";
import { rows } from "../CashFlow";
import { useState } from "react";
import LinesPanel, { type LinesTarget } from "../../components/LinesPanel";
import { monthLong, money, num, pct } from "../../money";
import { paceLine } from "../Goals";

/** "Data through Oct 22": the last day every account's data covers, and how many are late. */
export function DataThrough() {
  const status = useQuery({ queryKey: ["status"], queryFn: fetchStatus, staleTime: 5 * 60_000 });
  const sources = status.data?.sources ?? [];
  if (!sources.length) return null;
  const days = sources.map((x) => x.last_day).filter((d): d is string => !!d);
  const oldest = days.length ? days.reduce((a, b) => (a < b ? a : b)) : null;
  // The Gmail script gone silent counts too: nothing by email arrives until it runs again (ADR-078).
  const late =
    sources.filter((x) => x.state === "late" || x.state === "you_upload").length +
    (status.data?.script?.state === "silent" ? 1 : 0);
  return (
    <Link
      to="/status#arrivals"
      className={`pill ${late ? "bg-attention-bg text-attention-ink" : "pill-muted"} text-sm`}
    >
      {oldest ? `Complete through ${day(oldest)}` : "No data yet"}
      {late ? ` · ${late} ${late === 1 ? "source needs" : "sources need"} you` : ""}
    </Link>
  );
}

export function Customize({ shown, onChange }: { shown: string[]; onChange: (ids: string[]) => void }) {
  const hidden = ALL.filter((w) => !shown.includes(w));
  const move = (i: number, by: number) => {
    const next = [...shown];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    onChange(next);
  };
  return (
    <section className="card mt-6" aria-label="Customize Home">
      <h2 className="font-display text-xl font-bold">Your Home</h2>
      <p className="mt-1 text-sm text-muted">
        Show, hide and order the widgets. Saved for you on every device.
      </p>
      <ol className="mt-3 divide-y divide-line">
        {shown.map((w, i) => (
          <li key={w} className="flex items-center justify-between gap-2 py-2">
            <span className="font-medium">{WIDGETS[w]}</span>
            <span className="flex gap-1">
              <button
                type="button"
                className="btn btn-quiet h-9 px-3"
                aria-label={`Move ${WIDGETS[w]} up`}
                disabled={i === 0}
                onClick={() => move(i, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="btn btn-quiet h-9 px-3"
                aria-label={`Move ${WIDGETS[w]} down`}
                disabled={i === shown.length - 1}
                onClick={() => move(i, 1)}
              >
                ↓
              </button>
              <button
                type="button"
                className="btn btn-quiet h-9 px-3"
                onClick={() => onChange(shown.filter((x) => x !== w))}
              >
                Hide
              </button>
            </span>
          </li>
        ))}
        {hidden.map((w) => (
          <li key={w} className="flex items-center justify-between gap-2 py-2 text-muted">
            <span>{WIDGETS[w]} (hidden)</span>
            <button type="button" className="btn btn-quiet h-9 px-3" onClick={() => onChange([...shown, w])}>
              Show
            </button>
          </li>
        ))}
      </ol>
      <button type="button" className="btn btn-quiet mt-2" onClick={() => onChange(ALL)}>
        Back to the default
      </button>
    </section>
  );
}

export function Where({ f }: { f: Flows }) {
  const out = rows(f.flows)
    .filter((r) => r.side === "out" && r.amount > 0)
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 7);
  const top = Math.max(1, ...out.map((r) => r.amount));
  const ym = f.month.slice(0, 7);
  const [target, setTarget] = useState<LinesTarget | null>(null);
  return (
    <Card id="where" title="Where it went" link={[`/cashflow?month=${ym}`, "Cash flow"]}>
      {target && <LinesPanel target={target} onClose={() => setTarget(null)} />}
      {!out.length && <p className="text-muted">Nothing went out in {monthLong(f.month)}.</p>}
      <ul className="space-y-2">
        {out.map((r) => {
          const [side, id] = r.key.split(":");
          const n = Number(id.slice(1));
          const open = () =>
            setTarget({
              title: r.label,
              month: f.month,
              filter: id.startsWith("g")
                ? { side: side as "in" | "out", group_id: n }
                : { side: side as "in" | "out", category_id: n },
              moveTo: id.startsWith("c") ? n : null,
            });
          return (
            <li key={r.key}>
              <button
                type="button"
                onClick={open}
                className="block w-full rounded-lg text-left hover:bg-surface"
              >
                <span className="flex justify-between gap-3 text-sm">
                  <span>{r.label}</span>
                  <span className="num">{money(r.amount)}</span>
                </span>
                <span aria-hidden className="mt-1 block h-2 rounded-full bg-surface">
                  <span
                    className="block h-2 rounded-full"
                    style={{
                      width: `${(r.amount / top) * 100}%`,
                      background: r.color ?? "var(--color-flow-out)",
                    }}
                  />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-sm text-muted">Click a bar to see its lines and fix them.</p>
    </Card>
  );
}

export function Coming() {
  const projection = useQuery({ queryKey: ["projections"], queryFn: () => fetchProjection() });
  const p = projection.data;
  const items = p ? comingUp(p, p.today) : [];
  const total = items.reduce((s, i) => s + Math.abs(num(i.amount)), 0);
  return (
    <Card
      id="coming"
      title={`Coming up, next ${COMING_DAYS} days`}
      info="coming_up"
      link={["/recurring", "Bills"]}
    >
      {!p && <p className="text-muted">{projection.error ? "The forecast isn’t available." : "Loading…"}</p>}
      {p && !items.length && <p className="text-muted">No bills expected in the next {COMING_DAYS} days.</p>}
      <ul className="divide-y divide-line">
        {items.slice(0, 8).map((i) => (
          <li key={`${i.day}-${i.name}`} className="flex justify-between gap-3 py-2 text-sm">
            <span>
              <strong className="font-semibold">{i.name}</strong>
              <span className="block text-muted">{day(i.day)}</span>
            </span>
            <span className="num">{money(Math.abs(num(i.amount)))}</span>
          </li>
        ))}
      </ul>
      {items.length > 0 && (
        <p className="mt-2 flex justify-between border-t border-line pt-2 font-semibold">
          <span>Total due</span>
          <span className="num">{money(total)}</span>
        </p>
      )}
      {p?.lowest && (
        <p className={`mt-2 text-sm ${num(p.lowest.balance) < 0 ? "text-danger-ink" : "text-muted"}`}>
          Lowest cash ahead: <span className="num font-semibold">{money(p.lowest.balance)}</span> on{" "}
          {day(p.lowest.day)}.{" "}
          <Link to="/projections" className="text-primary underline">
            Forecast
          </Link>
        </p>
      )}
    </Card>
  );
}

export function Goals() {
  const sheet = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const saving = useQuery({ queryKey: ["goals"], queryFn: fetchGoals });
  const items = sheet.data?.items ?? [];
  const mine = (saving.data?.goals ?? []).filter((g) => g.is_active);
  const linked = new Set(mine.map((g) => g.item_key));
  // A purchase followed by a saving goal shows once, as the goal (ADR-040).
  const goals = items.filter((i) => i.is_active && i.purchase && !linked.has(i.key));
  const held = (people.data ?? [])
    .filter((p) => p.holding_id && p.is_active)
    .map((p) => ({ name: p.name, item: items.find((i) => i.holding_id === p.holding_id) }))
    .filter((h) => h.item && num(h.item.value) !== 0);
  return (
    <Card id="goals" title="Goals" info="goals" link={["/goals", "All goals"]}>
      {!sheet.data && <p className="text-muted">{sheet.error ? "Net worth isn’t available." : "Loading…"}</p>}
      {sheet.data && !goals.length && !held.length && !mine.length && (
        <p className="text-muted">No goals yet. Add one on Goals.</p>
      )}
      <ul className="space-y-4">
        {mine.map((g) => (
          <li key={`goal-${g.goal_id}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <strong>{g.name}</strong>
              <span className="num text-sm text-muted">
                {money(g.current)} of {money(g.target_amount)} · {pct(num(g.share))}
              </span>
            </div>
            <div
              className="mt-1 h-2 rounded-full bg-surface"
              role="progressbar"
              aria-label={`${g.name}: saved`}
              aria-valuenow={Math.round(num(g.share) * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="h-2 rounded-full bg-flow-in" style={{ width: `${num(g.share) * 100}%` }} />
            </div>
            <p className="mt-1 text-sm text-muted">{paceLine(g)}</p>
          </li>
        ))}
        {goals.map((g) => {
          const p = g.purchase!;
          const share = num(p.target) ? Math.min(1, num(p.paid) / num(p.target)) : 0;
          return (
            <li key={g.key}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <strong>{g.name}</strong>
                <span className="num text-sm text-muted">
                  {money(p.paid)} of {money(p.target)} · {pct(share)}
                </span>
              </div>
              <div
                className="mt-1 h-2 rounded-full bg-surface"
                role="progressbar"
                aria-label={`${g.name}: paid`}
                aria-valuenow={Math.round(share * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="h-2 rounded-full bg-flow-in" style={{ width: `${share * 100}%` }} />
              </div>
              {p.installments_left != null && p.installment && (
                <p className="num mt-1 text-sm text-muted">
                  {p.installments_left} × {money(p.installment)} left
                </p>
              )}
            </li>
          );
        })}
        {held.map((h) => (
          <li key={h.name} className="flex justify-between gap-3 text-sm">
            <span>
              <strong>Held for {h.name}</strong>
              <span className="block text-muted">Not yours: left out of what you kept</span>
            </span>
            <span className="num">{money(Math.abs(num(h.item!.value)))}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function InboxCard() {
  const review = useQuery({ queryKey: ["review", "count"], queryFn: () => fetchReview() });
  const r = review.data;
  return (
    <Card id="inbox" title="Inbox" link={["/review", "Review all"]}>
      {!r && <p className="text-muted">Loading…</p>}
      {r && !r.uncategorized_lines && <p className="text-good-ink">Every line has a category.</p>}
      {r && r.uncategorized_lines > 0 && (
        <>
          <p className="text-sm text-muted">
            {r.uncategorized_lines} {r.uncategorized_lines === 1 ? "line needs" : "lines need"} a category.
          </p>
          <ul className="mt-2 divide-y divide-line">
            {r.groups.slice(0, 4).map((g) => (
              <li
                key={g.merchant_key}
                className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
              >
                <span>
                  {g.merchant_key} · {g.lines.length} {g.lines.length === 1 ? "line" : "lines"}
                </span>
                {g.suggestion && (
                  <span className="pill pill-muted">
                    Claude: {g.suggestion.category_path} · {pct(num(g.suggestion.confidence))}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
