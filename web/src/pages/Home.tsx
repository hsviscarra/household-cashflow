import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  fetchBalanceSheet,
  fetchGoals,
  fetchFlows,
  fetchPeople,
  fetchProjection,
  fetchReview,
  fetchTodo,
  type Flows,
  type Projection,
} from "../api";
import KpiCard from "../components/KpiCard";
import { PersonNote } from "../components/Personalize";
import { localToday, money, monthLong, monthShort, num, pct } from "../money";
import { personParam, usePerson, useSettings } from "../prefs";
import { rows } from "./CashFlow";
import { paceLine } from "./Goals";

// Home (ADR-027): what needs you, the month in numbers, where it went, what's coming, goals and
// the Inbox, as widgets each person can hide and reorder ("Customize"), saved with their settings.

export const WIDGETS: Record<string, string> = {
  needs: "Needs you",
  kpis: "The month in numbers",
  where: "Where it went",
  coming: "Coming up",
  goals: "Goals",
  inbox: "Inbox",
};
const ALL = Object.keys(WIDGETS);
const COMING_DAYS = 14;

/** The person's widgets in their order; every widget when nothing is saved. */
export function useWidgets(): [string[], (ids: string[]) => void] {
  const { settings, set } = useSettings();
  const saved = (settings.home as { widgets?: unknown } | undefined)?.widgets;
  const shown = Array.isArray(saved) ? saved.filter((w): w is string => ALL.includes(w as string)) : ALL;
  return [shown, (ids) => set("home", { widgets: ids })];
}

const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return localToday(d);
};
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** Bills and purchases due from today through the next two weeks. */
export function comingUp(p: Projection, today: string, days = COMING_DAYS) {
  const end = addDays(today, days);
  return p.months
    .flatMap((m) => m.items)
    .filter((i) => (i.kind === "fixed" || i.kind === "purchase") && i.day >= today && i.day <= end)
    .sort((a, b) => a.day.localeCompare(b.day));
}

export default function Home() {
  const [person, , ready] = usePerson();
  const [widgets, setWidgets] = useWidgets();
  const [customizing, setCustomizing] = useState(false);
  const flows = useQuery({
    queryKey: ["cashflow", "flows", null, person],
    queryFn: () => fetchFlows(null, personParam(person)),
    enabled: ready,
  });
  const f = flows.data;

  const parts: Record<string, ReactNode> = {
    needs: <Needs key="needs" />,
    kpis: f ? <Numbers key="kpis" f={f} /> : null,
    where: f ? <Where key="where" f={f} /> : null,
    coming: <Coming key="coming" />,
    goals: <Goals key="goals" />,
    inbox: <InboxCard key="inbox" />,
  };

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-4xl font-bold leading-tight">
          {f && f.months.length ? monthLong(f.month) : "Home"}
        </h1>
        <button
          type="button"
          className="btn btn-secondary"
          aria-expanded={customizing}
          onClick={() => setCustomizing(!customizing)}
        >
          {customizing ? "Done" : "Customize"}
        </button>
      </div>
      <PersonNote person={person} />
      {customizing && <Customize shown={widgets} onChange={setWidgets} />}
      {flows.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the month: {(flows.error as Error).message}. Check that the database is connected and
          reload the page.
        </p>
      )}
      {f && !f.months.length && (
        <div className="mt-6 max-w-3xl">
          <h2 className="font-display text-2xl font-bold">No cash flow yet</h2>
          <p className="mt-2 text-lg text-muted">
            Load the Cash Flow workbook to see every month since August 2019; statements add the detail.
          </p>
          <Link to="/import" className="btn btn-primary mt-4">
            Load the Excel history
          </Link>
        </div>
      )}
      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        {widgets.map((w) => (
          <div key={w} className={w === "needs" || w === "kpis" ? "lg:col-span-2" : undefined}>
            {parts[w]}
          </div>
        ))}
      </div>
      {!widgets.length && (
        <p className="mt-6 text-muted">Every widget is hidden. Use Customize to bring some back.</p>
      )}
    </section>
  );
}

function Customize({ shown, onChange }: { shown: string[]; onChange: (ids: string[]) => void }) {
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

function Card({
  id,
  title,
  link,
  children,
}: {
  id: string;
  title: string;
  link?: [string, string];
  children: ReactNode;
}) {
  return (
    <section className="card h-full" aria-labelledby={id}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={id} className="font-display text-xl font-bold">
          {title}
        </h2>
        {link && (
          <Link to={link[0]} className="text-sm font-semibold text-primary">
            {link[1]} →
          </Link>
        )}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Needs() {
  // Everything to do lives on To do (ADR-047); Home shows how much, by kind.
  const todo = useQuery({ queryKey: ["todo"], queryFn: fetchTodo, staleTime: 5 * 60_000 });
  const projection = useQuery({ queryKey: ["projections"], queryFn: () => fetchProjection() });
  const items: { text: string; to: string }[] = (todo.data?.sections ?? []).map((s) => ({
    text: `${s.title}: ${s.count}`,
    to: `/todo#${s.key}`,
  }));
  const low = projection.data?.lowest;
  if (low && num(low.balance) < 0)
    items.push({ text: `Cash runs short on ${day(low.day)} (${money(low.balance)})`, to: "/projections" });
  if (!items.length)
    return (
      <p className="rounded-2xl bg-good-bg px-4 py-3 text-good-ink">
        <strong>Nothing needs you.</strong> Every line has a category and the statements are in.
      </p>
    );
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
      <strong>Needs you:</strong>
      {items.map((i, k) => (
        <span key={i.text} className="flex items-center gap-3">
          {k > 0 && <span aria-hidden>·</span>}
          <Link to={i.to} className="font-semibold underline">
            {i.text}
          </Link>
        </span>
      ))}
    </div>
  );
}

function Numbers({ f }: { f: Flows }) {
  const sheet = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const projection = useQuery({ queryKey: ["projections"], queryFn: () => fetchProjection() });
  const list = rows(f.flows);
  const sum = (side: "in" | "out", key: "amount" | "prev") =>
    list.filter((r) => r.side === side).reduce((s, r) => s + r[key], 0);
  const [moneyIn, moneyOut] = [sum("in", "amount"), sum("out", "amount")];
  const [prevIn, prevOut] = [sum("in", "prev"), sum("out", "prev")];
  const vs = (now: number, before: number) =>
    before
      ? `${now >= before ? "+" : "−"}${Math.abs(Math.round(((now - before) / before) * 100))}% vs ${monthShort(f.prev_month)}`
      : undefined;
  const low = projection.data?.lowest;
  return (
    <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <KpiCard
        label="Money in"
        value={money(moneyIn)}
        note={vs(moneyIn, prevIn)}
        tone={moneyIn >= prevIn ? "good" : "bad"}
      />
      <KpiCard
        label="Money out"
        value={money(moneyOut)}
        note={vs(moneyOut, prevOut)}
        tone={moneyOut <= prevOut ? "good" : "bad"}
      />
      <KpiCard
        label="Kept"
        value={money(moneyIn - moneyOut)}
        note={moneyIn ? `${pct((moneyIn - moneyOut) / moneyIn)} of money in` : undefined}
        tone={moneyIn - moneyOut < 0 ? "bad" : undefined}
      />
      {sheet.data && (
        <KpiCard
          label="Net worth"
          value={money(sheet.data.net_worth)}
          note={`as of ${day(sheet.data.as_of)}`}
        />
      )}
      {low && (
        <KpiCard
          label="Lowest cash ahead"
          value={money(low.balance)}
          note={`on ${day(low.day)}`}
          tone={num(low.balance) < 0 ? "attention" : undefined}
        />
      )}
    </dl>
  );
}

function Where({ f }: { f: Flows }) {
  const out = rows(f.flows)
    .filter((r) => r.side === "out" && r.amount > 0)
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 7);
  const top = Math.max(1, ...out.map((r) => r.amount));
  const ym = f.month.slice(0, 7);
  return (
    <Card id="where" title="Where it went" link={[`/cashflow?month=${ym}`, "Cash flow"]}>
      {!out.length && <p className="text-muted">Nothing went out in {monthLong(f.month)}.</p>}
      <ul className="space-y-2">
        {out.map((r) => {
          const [side, id] = r.key.split(":");
          const to = `/cashflow?month=${ym}&side=${side}&${id.startsWith("g") ? "g" : "c"}=${id.slice(1)}`;
          return (
            <li key={r.key}>
              <Link to={to} className="block rounded-lg hover:bg-surface">
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
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-sm text-muted">Click a bar to open its categories, merchants and lines.</p>
    </Card>
  );
}

function Coming() {
  const projection = useQuery({ queryKey: ["projections"], queryFn: () => fetchProjection() });
  const p = projection.data;
  const items = p ? comingUp(p, p.today) : [];
  const total = items.reduce((s, i) => s + Math.abs(num(i.amount)), 0);
  return (
    <Card id="coming" title={`Coming up, next ${COMING_DAYS} days`} link={["/recurring", "Bills"]}>
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
    </Card>
  );
}

function Goals() {
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
    <Card id="goals" title="Goals" link={["/goals", "All goals"]}>
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

function InboxCard() {
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
