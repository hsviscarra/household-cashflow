import { useQuery } from "@tanstack/react-query";
import {
  fetchSafeToSpend,
  fetchTodo,
  fetchProjection,
  type MeasurePeriod,
  type MonthMeasures,
  fetchBalanceSheet,
  type SheetItem,
} from "../../api";
import { Card, day, monthEnd } from "./shared";
import SafeToSpend from "../../components/SafeToSpend";
import { num, money, monthShort, monthLong, localToday } from "../../money";
import { Link } from "react-router-dom";
import { useState } from "react";
import LinesPanel, { type LinesTarget } from "../../components/LinesPanel";
import Info from "../../components/Info";
import KpiCard from "../../components/KpiCard";
import { TrendLine } from "../../components/charts";

/** What is left for the rest of this month after bills and goals (ADR-097). Always the month
 * running now, whichever month the page shows. */
export function Safe() {
  const q = useQuery({ queryKey: ["savings", "safe"], queryFn: fetchSafeToSpend, staleTime: 5 * 60_000 });
  return (
    <Card id="safe" title="Safe to spend" link={["/savings", "Saving"]}>
      {q.error && <p className="text-muted">Not available right now.</p>}
      {!q.data && !q.error && <p className="text-muted">Loading…</p>}
      {q.data && <SafeToSpend safe={q.data} />}
    </Card>
  );
}

export function Needs() {
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

export const range = (p: MeasurePeriod) =>
  p.start.slice(8) === "01" && p.end === monthEnd(p.month)
    ? monthShort(p.month)
    : `${monthShort(p.month)} ${Number(p.start.slice(8))}–${Number(p.end.slice(8))}`;

/** The month so far in four measures (ADR-073), each against the same days of the month before. */
export function Numbers({ m }: { m: MonthMeasures }) {
  const [target, setTarget] = useState<LinesTarget | null>(null);
  const t = m.this;
  const b = m.before;
  const vs = (key: keyof MeasurePeriod, goodWhenUp: boolean) => {
    const now = num(t[key]);
    const was = num(b[key]);
    const label = `vs ${range(b)}: ${money(was)}`;
    if (!was) return { note: label, tone: undefined };
    const up = now >= was;
    return {
      note: `${up ? "+" : "−"}${Math.abs(Math.round(((now - was) / Math.abs(was)) * 100))}% ${label}`,
      tone: (up === goodWhenUp ? "good" : "bad") as "good" | "bad",
    };
  };
  const cards: [keyof MeasurePeriod, string, "money_in" | "spent" | "set_aside" | "left_over", boolean][] = [
    ["money_in", "Money in", "money_in", true],
    ["spent", "Spent", "spent", false],
    ["set_aside", "Set aside", "set_aside", true],
    ["left_over", "Left over", "left_over", true],
  ];
  return (
    <section aria-labelledby="kpis">
      <h2 id="kpis" className="mb-2 flex items-center gap-2 font-display text-xl font-bold">
        {m.running ? `${monthShort(m.month)} 1–${Number(m.through.slice(8))} so far` : monthLong(m.month)}
        <Info k="same_days" />
      </h2>
      {target && <LinesPanel target={target} onClose={() => setTarget(null)} />}
      <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {cards.map(([key, label, k, up]) => {
          const c = vs(key, up);
          return (
            <div key={key} className="relative">
              <span className="absolute right-3 top-3 z-10">
                <Info k={k} />
              </span>
              <KpiCard
                label={label}
                value={money(t[key])}
                note={c.note}
                tone={key === "left_over" && num(t[key]) < 0 ? "bad" : c.tone}
                onOpen={
                  key === "money_in" || key === "spent"
                    ? () =>
                        setTarget({
                          title: label,
                          month: m.month,
                          filter: { side: key === "money_in" ? "in" : "out" },
                        })
                    : undefined
                }
              />
            </div>
          );
        })}
      </dl>
    </section>
  );
}

export const STALE_DAYS = 35;

/** Each bank account's balance as the bank shows it, with its date (ADR-073). */
export function MoneyNow() {
  const sheet = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const today = localToday();
  const items = (sheet.data?.items ?? []).filter(
    (i) => i.is_active && (i.holding_class === "cash" || i.holding_class === "card") && i.value !== null,
  );
  const cash = items.filter((i) => i.holding_class === "cash").sort((a, b) => num(b.value) - num(a.value));
  const cards = items.filter((i) => i.holding_class === "card" && num(i.value) !== 0);
  const stale = (i: SheetItem) => !i.as_of || (Date.parse(today) - Date.parse(i.as_of)) / 864e5 > STALE_DAYS;
  const total = cash.reduce((s, i) => s + num(i.value), 0);
  const owed = cards.reduce((s, i) => s + num(i.value), 0);
  const oldest = cash
    .map((i) => i.as_of ?? "")
    .filter(Boolean)
    .sort()[0];
  const row = (i: SheetItem) => (
    <li key={i.key} className="flex items-baseline justify-between gap-3 py-1.5 text-sm">
      <span className={stale(i) ? "text-muted" : ""}>
        {i.name}
        <span className="block text-xs text-muted">
          {i.as_of ? `${i.source === "bank_sync" ? "synced" : "statement"} ${day(i.as_of)}` : "no date"}
          {stale(i) ? " · not updated" : ""}
        </span>
      </span>
      <span className={`num ${stale(i) ? "text-muted" : ""}`}>{money(i.value)}</span>
    </li>
  );
  return (
    <Card id="money" title="Your money now" info="money_now" link={["/debt", "Net worth"]}>
      {!sheet.data && <p className="text-muted">{sheet.error ? "Balances aren’t available." : "Loading…"}</p>}
      {sheet.data && (
        <>
          <p className="num font-display text-3xl font-bold">{money(total)}</p>
          <p className="text-sm text-muted">
            in {cash.length} accounts{oldest ? `, the oldest as of ${day(oldest)}` : ""}
            {owed ? ` · ${money(owed)} owed on cards` : ""}
          </p>
          <ul className="mt-2 divide-y divide-line">{cash.map(row)}</ul>
          {cards.length > 0 && (
            <>
              <p className="label mt-3">Cards owed</p>
              <ul className="divide-y divide-line">{cards.map(row)}</ul>
            </>
          )}
        </>
      )}
    </Card>
  );
}

export const CLASSES: [string, string, string][] = [
  ["cash", "Cash", "var(--color-cat-transport)"],
  ["investment", "Investments", "var(--color-cat-groceries)"],
  ["property", "Properties", "var(--color-cat-dining)"],
  ["purchase", "New house", "var(--color-cat-services)"],
  ["vehicle", "Car", "var(--color-cat-shopping)"],
];

export function NetWorth() {
  const sheet = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const s = sheet.data;
  const series = (s?.series ?? []).slice(-24);
  const last = series.at(-1);
  const monthAgo = series.at(-2);
  const jan = series.find(
    (p) => p.month.slice(5, 7) === "01" && p.month.slice(0, 4) === localToday().slice(0, 4),
  );
  const change = (p?: { net: string }) => (p && s ? num(s.net_worth) - num(p.net) : null);
  const by = (cls: string) =>
    (s?.items ?? [])
      .filter((i) => i.is_active && i.holding_class === cls && i.side === "asset")
      .reduce((t, i) => t + num(i.value), 0);
  const assets = CLASSES.map(([k, label, color]) => ({ k, label, color, v: by(k) })).filter((c) => c.v > 0);
  const totalAssets = assets.reduce((t, c) => t + c.v, 0) || 1;
  const signed = (v: number | null) => (v === null ? "—" : `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`);
  return (
    <Card id="networth" title="Net worth" info="net_worth" link={["/debt", "Balance sheet"]}>
      {!s && <p className="text-muted">{sheet.error ? "Net worth isn’t available." : "Loading…"}</p>}
      {s && (
        <>
          <p className="num font-display text-3xl font-bold">{money(s.net_worth)}</p>
          <p className="num text-sm text-muted">
            {signed(change(monthAgo))} this month · {signed(change(jan))} this year · owe{" "}
            {money(s.liabilities)}
          </p>
          {series.length > 1 && (
            <TrendLine
              title="Net worth by month"
              data={series.map((p, i) => ({
                key: p.month,
                value: num(p.net),
                tick: (series.length - 1 - i) % 3 === 0 ? monthShort(p.month) : undefined,
                tooltip: (
                  <>
                    <p className="font-semibold">{monthLong(p.month)}</p>
                    <p className="num">{money(p.net)}</p>
                  </>
                ),
              }))}
            />
          )}
          <div className="mt-2 flex h-3 overflow-hidden rounded-full" aria-hidden>
            {assets.map((c) => (
              <span key={c.k} style={{ width: `${(c.v / totalAssets) * 100}%`, background: c.color }} />
            ))}
          </div>
          <ul className="mt-2 grid grid-cols-2 gap-x-4 text-sm">
            {assets.map((c) => (
              <li key={c.k} className="flex justify-between gap-2">
                <span className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ background: c.color }}
                  />
                  {c.label}
                </span>
                <span className="num">{money(c.v)}</span>
              </li>
            ))}
          </ul>
          {last && <p className="mt-1 text-xs text-muted">As of {day(s.as_of)}.</p>}
        </>
      )}
    </Card>
  );
}
