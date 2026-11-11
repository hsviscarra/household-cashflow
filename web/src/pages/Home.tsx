import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  fetchBalanceSheet,
  fetchBudget,
  fetchGoals,
  fetchFlows,
  fetchMeasures,
  fetchPeople,
  fetchPortfolio,
  fetchProjection,
  fetchReview,
  fetchStatus,
  fetchTodo,
  type Flows,
  type MeasurePeriod,
  type MonthMeasures,
  type Projection,
  type SheetItem,
} from "../api";
import { Legend, StackedColumns, TrendLine } from "../components/charts";
import Info from "../components/Info";
import KpiCard from "../components/KpiCard";
import LinesPanel, { type LinesTarget } from "../components/LinesPanel";
import { PersonNote } from "../components/Personalize";
import type { ExplainKey } from "../explain";
import { addMonths, localToday, money, monthLong, monthShort, num, pct } from "../money";
import { personParam, usePerson, useSettings } from "../prefs";
import { rows } from "./CashFlow";
import { paceLine } from "./Goals";

// Home (ADR-027, ADR-073): how much money there is now, how the month is going, what you are
// building (net worth, investments, the house, goals) and what needs you, as widgets each person
// can hide and reorder ("Customize"). A month picker changes every block.

export const WIDGETS: Record<string, string> = {
  needs: "Needs you",
  kpis: "This month so far",
  money: "Your money now",
  networth: "Net worth",
  cashflow: "Cash flow, 12 months",
  investments: "Investments",
  budget: "Budget: planned vs actual",
  goals: "Goals",
  coming: "Coming up",
  where: "Where it went",
  inbox: "Inbox",
};
const LAYOUT = 2; // saved widget lists from before this layout start from the new default
const ALL = Object.keys(WIDGETS);
const COMING_DAYS = 14;

/** The person's widgets in their order; every widget when nothing is saved. */
export function useWidgets(): [string[], (ids: string[]) => void] {
  const { settings, set } = useSettings();
  const home = settings.home as { widgets?: unknown; layout?: number } | undefined;
  const saved = home?.layout === LAYOUT ? home.widgets : undefined;
  const shown = Array.isArray(saved) ? saved.filter((w): w is string => ALL.includes(w as string)) : ALL;
  return [shown, (ids) => set("home", { widgets: ids, layout: LAYOUT })];
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
  const [params, setParams] = useSearchParams();
  const thisMonth = `${localToday().slice(0, 7)}`;
  const ym = /^\d{4}-\d{2}$/.test(params.get("month") ?? "") ? params.get("month")! : thisMonth;
  const month = `${ym}-01`;
  const go = (by: number) => {
    const next = addMonths(month, by).slice(0, 7);
    setParams(next === thisMonth ? {} : { month: next }, { replace: true });
  };
  const flows = useQuery({
    queryKey: ["cashflow", "flows", month, person],
    queryFn: () => fetchFlows(month, personParam(person)),
    enabled: ready,
  });
  const measures = useQuery({
    queryKey: ["cashflow", "measures", month, person],
    queryFn: () => fetchMeasures(month, personParam(person)),
    enabled: ready,
  });
  const f = flows.data;
  const m = measures.data;

  const parts: Record<string, ReactNode> = {
    needs: <Needs key="needs" />,
    kpis: m ? <Numbers key="kpis" m={m} /> : null,
    money: <MoneyNow key="money" />,
    networth: <NetWorth key="networth" />,
    cashflow: m ? <CashFlow12 key="cashflow" m={m} /> : null,
    investments: <Investments key="investments" />,
    budget: <Budget key="budget" month={month} />,
    goals: <Goals key="goals" />,
    coming: <Coming key="coming" />,
    where: f ? <Where key="where" f={f} /> : null,
    inbox: <InboxCard key="inbox" />,
  };
  const wide = new Set(["needs", "kpis"]);

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary px-3"
            aria-label="Month before"
            onClick={() => go(-1)}
          >
            ‹
          </button>
          <h1 className="font-display text-4xl font-bold leading-tight">{monthLong(month)}</h1>
          <button
            type="button"
            className="btn btn-secondary px-3"
            aria-label="Month after"
            disabled={ym >= thisMonth}
            onClick={() => go(1)}
          >
            ›
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DataThrough />
          <button
            type="button"
            className="btn btn-secondary"
            aria-expanded={customizing}
            onClick={() => setCustomizing(!customizing)}
          >
            {customizing ? "Done" : "Customize"}
          </button>
        </div>
      </div>
      <PersonNote person={person} />
      {customizing && <Customize shown={widgets} onChange={setWidgets} />}
      {(flows.error || measures.error) && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the month: {((flows.error || measures.error) as Error).message}. Reload the page; if
          the database was asleep it wakes up in about a minute.
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
          <div key={w} className={wide.has(w) ? "lg:col-span-2" : undefined}>
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

/** "Data through Oct 22": the last day every account's data covers, and how many are late. */
function DataThrough() {
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
  info,
  link,
  children,
}: {
  id: string;
  title: string;
  info?: ExplainKey;
  link?: [string, string];
  children: ReactNode;
}) {
  return (
    <section className="card h-full" aria-labelledby={id}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-2">
          <h2 id={id} className="font-display text-xl font-bold">
            {title}
          </h2>
          {info && <Info k={info} />}
        </span>
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

const range = (p: MeasurePeriod) =>
  p.start.slice(8) === "01" && p.end === monthEnd(p.month)
    ? monthShort(p.month)
    : `${monthShort(p.month)} ${Number(p.start.slice(8))}–${Number(p.end.slice(8))}`;
const monthEnd = (iso: string) => {
  const d = new Date(`${addMonths(iso, 1)}T00:00:00`);
  d.setDate(0);
  return localToday(d);
};

/** The month so far in four measures (ADR-073), each against the same days of the month before. */
function Numbers({ m }: { m: MonthMeasures }) {
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

const STALE_DAYS = 35;

/** Each bank account's balance as the bank shows it, with its date (ADR-073). */
function MoneyNow() {
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

const CLASSES: [string, string, string][] = [
  ["cash", "Cash", "var(--color-cat-transport)"],
  ["investment", "Investments", "var(--color-cat-groceries)"],
  ["property", "Properties", "var(--color-cat-dining)"],
  ["purchase", "New house", "var(--color-cat-services)"],
  ["vehicle", "Car", "var(--color-cat-shopping)"],
];

function NetWorth() {
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

function CashFlow12({ m }: { m: MonthMeasures }) {
  const data = m.months.map((p) => {
    const partial = p.end !== monthEnd(p.month);
    return {
      key: p.month.slice(0, 7),
      label: `${monthShort(p.month)}${partial ? "*" : ""}`,
      selected: p.month === m.month,
      line: num(p.money_in),
      segments: [
        { key: "spent", value: num(p.spent), color: "var(--color-flow-out)" },
        { key: "set_aside", value: num(p.set_aside), color: "var(--color-cat-groceries)" },
      ],
      tooltip: (
        <>
          <p className="font-semibold">
            {monthLong(p.month)}
            {partial ? ` (to ${day(p.end)})` : ""}
          </p>
          <p className="num">In {money(p.money_in)}</p>
          <p className="num">Spent {money(p.spent)}</p>
          <p className="num">Set aside {money(p.set_aside)}</p>
          <p className="num font-semibold">Left over {money(p.left_over)}</p>
        </>
      ),
    };
  });
  const [, setParams] = useSearchParams();
  return (
    <Card
      id="cashflow12"
      title="Cash flow, 12 months"
      link={[`/cashflow?month=${m.month.slice(0, 7)}`, "Cash flow"]}
    >
      <StackedColumns
        data={data}
        title="Money in, spent and set aside by month"
        onSelect={(k) => setParams(k === localToday().slice(0, 7) ? {} : { month: k })}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Legend
          items={[
            { label: "Spent", color: "var(--color-flow-out)" },
            { label: "Set aside", color: "var(--color-cat-groceries)" },
          ]}
        />
        <span className="flex items-center gap-2 text-sm text-muted">
          <span aria-hidden className="inline-block h-0.5 w-5 bg-ink" /> Money in
        </span>
      </div>
      <p className="mt-1 text-xs text-muted">* month still running. Click a month to look at it.</p>
    </Card>
  );
}

function Investments() {
  const p = useQuery({ queryKey: ["ibkr"], queryFn: fetchPortfolio });
  const d = p.data;
  const top = (d?.positions ?? [])
    .slice()
    .sort((a, b) => num(b.value) - num(a.value))
    .slice(0, 5);
  const gain = (d?.positions ?? []).reduce((s, x) => s + num(x.unrealized), 0);
  const change = d?.previous_total ? num(d.total) - num(d.previous_total) : null;
  return (
    <Card id="investments" title="Investments" info="investments" link={["/debt", "Net worth"]}>
      {!d && <p className="text-muted">{p.error ? "Investments aren’t available." : "Loading…"}</p>}
      {d && !d.total && <p className="text-muted">No Interactive Brokers data yet.</p>}
      {d && d.total && (
        <>
          <p className="num font-display text-3xl font-bold">{money(d.total)}</p>
          <p className="num text-sm text-muted">
            {change !== null
              ? `${change >= 0 ? "+" : "−"}${money(Math.abs(change))} since ${day(d.previous_as_of!)} · `
              : ""}
            {gain >= 0 ? "+" : "−"}
            {money(Math.abs(gain))} gain since bought · as of {day(d.as_of!)}
            {d.stale ? " · not updated" : ""}
          </p>
          <ul className="mt-2 divide-y divide-line">
            {top.map((x) => (
              <li key={x.symbol} className="flex justify-between gap-3 py-1.5 text-sm">
                <span className="font-semibold">{x.symbol}</span>
                <span className="num">
                  {money(x.value)}
                  {x.unrealized && (
                    <span
                      className={`ml-2 text-xs ${num(x.unrealized) >= 0 ? "text-good-ink" : "text-danger-ink"}`}
                    >
                      {num(x.unrealized) >= 0 ? "+" : "−"}
                      {money(Math.abs(num(x.unrealized)))}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

const BUDGET_TONE: Record<string, string> = {
  over: "bg-danger-ink",
  ahead: "bg-attention-ink",
  on_track: "bg-flow-in",
  none: "bg-line",
};

function Budget({ month }: { month: string }) {
  const ym = month.slice(0, 7);
  const b = useQuery({ queryKey: ["budget", ym], queryFn: () => fetchBudget(ym) });
  const d = b.data;
  const groups = (d?.groups ?? [])
    .filter((g) => g.budget !== null)
    .sort((x, y) => num(y.spent) - num(x.spent));
  return (
    <Card id="budget" title="Budget: planned vs actual" info="budget" link={["/budget", "Budget"]}>
      {!d && <p className="text-muted">{b.error ? "The budget isn’t available." : "Loading…"}</p>}
      {d && !groups.length && (
        <p className="text-muted">
          No budget yet.{" "}
          <Link to="/budget" className="text-primary underline">
            Start one from your averages
          </Link>
          .
        </p>
      )}
      {d && groups.length > 0 && (
        <>
          <p className="num text-sm text-muted">
            {money(d.spent)} spent of {money(d.budgeted)} planned · {money(d.left)} left
          </p>
          <ul className="mt-2 space-y-2">
            {groups.slice(0, 8).map((g) => {
              const avail = Math.max(1, num(g.available));
              const share = Math.min(1, num(g.spent) / avail);
              const pace = Math.min(1, num(d.day_share));
              return (
                <li key={g.group_id}>
                  <span className="flex justify-between gap-3 text-sm">
                    <span>{g.name}</span>
                    <span className="num">
                      {money(g.spent)} <span className="text-muted">of {money(g.available)}</span>
                    </span>
                  </span>
                  <span aria-hidden className="relative mt-1 block h-2 rounded-full bg-surface">
                    <span
                      className={`block h-2 rounded-full ${BUDGET_TONE[g.status]}`}
                      style={{ width: `${share * 100}%` }}
                    />
                    <span className="absolute -top-0.5 h-3 w-0.5 bg-ink" style={{ left: `${pace * 100}%` }} />
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-xs text-muted">
            The thin mark is where spending would be on pace for today.
          </p>
        </>
      )}
    </Card>
  );
}

function Where({ f }: { f: Flows }) {
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

function Coming() {
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
