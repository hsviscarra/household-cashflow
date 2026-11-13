import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  DEFAULT_FORECAST,
  fetchAccounts,
  fetchProjection,
  runScenario,
  type ForecastChange,
  type ForecastOptions,
  type Projection,
  type ProjectionMonth,
} from "../api";
import { CashLines, type CashSeries } from "../components/flowcharts";
import Scenarios from "../components/Scenarios";
import { localToday, money, monthLong, monthShort, num } from "../money";
import { useSettings } from "../prefs";

const LINE_COLORS = ["var(--color-flow-out)", "#C2410C", "#0F766E", "#9A3412", "#6B6788"];
const HORIZON: Record<number, string> = { 1: "1 month", 3: "3 months", 12: "12 months" };

/** The forecast choices, saved for the person (ADR-026). */
function useForecastOptions(): [ForecastOptions, (o: Partial<ForecastOptions>) => void] {
  const { settings, set } = useSettings();
  const saved = (settings.forecast ?? {}) as Partial<ForecastOptions>;
  const o = { ...DEFAULT_FORECAST, ...saved };
  return [o, (patch) => set("forecast", { ...o, ...patch })];
}

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const signedMoney = (v: string | number) =>
  `${num(v) < 0 ? "−" : num(v) > 0 ? "+" : ""}${money(Math.abs(num(v)))}`;

/** "Next 3 months: −5,016.63; lowest cash −2,231.66 on Jan 20, before Hernan (Salaries) on Jan 21." */
export function projectionHeadline(p: Projection): string {
  const net = p.months.reduce((sum, m) => sum + num(m.net), 0);
  let text = `Next ${p.months.length} ${p.months.length === 1 ? "month" : "months"}: ${signedMoney(net)}`;
  if (p.lowest) {
    text += `; lowest cash ${signedMoney(p.lowest.balance).replace(/^\+/, "")} on ${day(p.lowest.day)}`;
    if (p.next_payday) text += `, before ${p.next_payday.name} on ${day(p.next_payday.day)}`;
  }
  return `${text}.`;
}

/** "In 8 of 10 cases cash ends January between 1,200.00 and 4,800.00. About a 15% chance it
 * goes under zero on the way." Empty without enough history for a range (ADR-096). */
export function rangeLine(p: Projection): string {
  const last = p.months[p.months.length - 1];
  if (!last || last.end_cash_low == null || last.end_cash_high == null) return "";
  const floor = num(p.floor ?? 0);
  const under = floor > 0 ? `your ${money(floor)} floor` : "zero";
  const chance = p.chance_under_floor == null ? null : Math.round(num(p.chance_under_floor) * 100);
  const risk =
    chance == null
      ? ""
      : chance === 0
        ? ` It stays over ${under} in every case tried.`
        : chance === 100
          ? ` It goes under ${under} on the way in every case tried.`
          : ` About a ${chance}% chance it goes under ${under} on the way.`;
  return `In 8 of 10 cases cash ends ${monthLong(last.month)} between ${minus(last.end_cash_low)} and ${minus(last.end_cash_high)}.${risk}`;
}

export default function ProjectionsPage() {
  const [opts, setOpts] = useForecastOptions();
  const [changes, setChanges] = useState<ForecastChange[]>([]);
  const q = useQuery({
    queryKey: ["projections", opts, changes],
    queryFn: () => (changes.length ? runScenario(opts, changes) : fetchProjection(opts)),
    placeholderData: (old) => old,
  });
  const p = q.data;
  const n = p?.months.length ?? opts.horizon;
  const totals = p
    ? {
        income: p.months.reduce((s, m) => s + num(m.income), 0),
        out: p.months.reduce((s, m) => s + num(m.fixed) + num(m.variable) + num(m.purchases), 0),
      }
    : null;
  const short = p?.lowest && num(p.lowest.balance) < 0;
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {p ? projectionHeadline(p) : "Projections"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        Will cash cover what’s coming? From your bills and income, your usual everyday spending and the
        purchase installments, starting from your bank balances.
      </p>
      <div role="group" aria-label="Horizon" className="mt-4 inline-flex rounded-xl bg-surface p-1 text-sm">
        {[1, 3, 12].map((h) => (
          <button
            key={h}
            type="button"
            aria-pressed={opts.horizon === h}
            className={`h-9 rounded-lg px-3 font-semibold ${opts.horizon === h ? "bg-ground text-ink shadow-sm" : "text-muted"}`}
            onClick={() => setOpts({ horizon: h })}
          >
            {HORIZON[h]}
          </button>
        ))}
      </div>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the projection: {(q.error as Error).message}
        </p>
      )}
      {!p && !q.error && <p className="mt-6 text-muted">Projecting the next months…</p>}
      {p && totals && (
        <>
          {short && (
            <p className="mt-4 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink">
              Cash runs short: {money(Math.abs(num(p.lowest!.balance)))} below zero on {day(p.lowest!.day)}.
              Move money in before then or delay a payment.
            </p>
          )}
          <HeadsUp p={p} />
          <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile
              label="Cash today"
              value={money(p.start_cash)}
              hint={p.cash_as_of ? `bank statements to ${day(p.cash_as_of)}` : "no bank statement yet"}
            />
            <Tile label={`Money in, ${n} ${n === 1 ? "month" : "months"}`} value={money(totals.income)} />
            <Tile label={`Money out, ${n} ${n === 1 ? "month" : "months"}`} value={money(totals.out)} />
            <Tile
              label={`Cash at the end of ${monthShort(p.months[p.months.length - 1].month)}`}
              value={signedMoney(p.months[p.months.length - 1].end_cash).replace(/^\+/, "")}
              hint={
                p.months[p.months.length - 1].end_cash_low != null
                  ? `likely ${minus(p.months[p.months.length - 1].end_cash_low!)} to ${minus(p.months[p.months.length - 1].end_cash_high!)}`
                  : undefined
              }
            />
          </dl>
          {rangeLine(p) && (
            <p className="mt-3 text-muted" aria-label="Likely range">
              {rangeLine(p)} The range comes from how much your total spending really varied month to month
              over the last two years; income and bills are taken as planned.
            </p>
          )}

          <h2 className="mt-10 font-display text-2xl font-bold">Month by month</h2>
          <div className="mt-3 overflow-x-auto rounded-2xl border border-line">
            <table className="w-full text-sm">
              <caption className="sr-only">Projection for the next {p.months.length} months</caption>
              <thead className="bg-surface text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">
                    &nbsp;
                  </th>
                  {p.months.map((m) => (
                    <th key={m.month} scope="col" className="px-3 py-2 text-right font-semibold">
                      {monthLong(m.month)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                <Row label="Income (recurring)" months={p.months} pick={(m) => money(m.income)} />
                <Row label="Fixed outflows (recurring)" months={p.months} pick={(m) => money(m.fixed)} />
                <Row
                  label={
                    p.seasonal_groups ? "Everyday spending (with seasons)" : "Everyday spending (average)"
                  }
                  months={p.months}
                  pick={(m) => money(m.variable)}
                />
                <Row label="Purchase installments" months={p.months} pick={(m) => money(m.purchases)} />
                <Row label="Net" months={p.months} pick={(m) => signedMoney(m.net)} strong />
                <Row
                  label="Cash at month end"
                  months={p.months}
                  pick={(m) => signedMoney(m.end_cash).replace(/^\+/, "")}
                  strong
                />
                {p.months.some((m) => m.end_cash_low != null) && (
                  <Row
                    label="Likely range"
                    months={p.months}
                    pick={(m) =>
                      m.end_cash_low != null && m.end_cash_high != null
                        ? `${minus(m.end_cash_low)} to ${minus(m.end_cash_high)}`
                        : "—"
                    }
                  />
                )}
              </tbody>
            </table>
          </div>
          <Seasons months={p.months} />
          <p className="mt-2 text-sm text-muted">
            Everyday spending starts from the average of{" "}
            {p.average_months.length
              ? p.average_months.map((m) => monthShort(m)).join(", ")
              : "no complete month yet"}
            : money spent from the bank that no recurring item paid. Card purchases are in the card payments.{" "}
            <Link className="text-primary underline" to="/recurring">
              Change the recurring items
            </Link>
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {p.months.map((m) => (
              <details key={m.month} className="rounded-2xl border border-line p-3 text-sm">
                <summary className="cursor-pointer font-semibold">
                  {monthLong(m.month)} · {m.items.length} {m.items.length === 1 ? "item" : "items"}
                </summary>
                <ul className="mt-2 divide-y divide-line" aria-label={`Items in ${monthLong(m.month)}`}>
                  {m.items.map((e, i) => (
                    <li key={i} className="flex justify-between gap-2 py-1">
                      <span>
                        <span className="num">{day(e.day)}</span> <span className="text-muted">·</span>{" "}
                        {e.name}
                      </span>
                      <span className="num">{signedMoney(e.amount)}</span>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>

          <div className="mt-10 grid gap-6 xl:grid-cols-2">
            <Assumptions p={p} opts={opts} setOpts={setOpts} />
            <WhatIfs changes={changes} setChanges={setChanges} p={p} />
          </div>
          <Scenarios opts={opts} changes={changes} setChanges={setChanges} />

          <h2 className="mt-10 font-display text-2xl font-bold">Cash day by day</h2>
          <div className="mt-3 rounded-2xl bg-surface p-4 md:p-6">
            <CashLines
              title={`Projected cash from ${day(p.daily[0].day)} to ${day(p.daily[p.daily.length - 1].day)}`}
              floor={num(p.floor ?? 0)}
              band={p.band}
              series={[
                { key: "total", label: "All bank accounts", color: "var(--color-primary)", points: p.daily },
                ...(p.accounts ?? []).map((a, i): CashSeries => ({
                  key: String(a.account_id),
                  label: a.name,
                  color: LINE_COLORS[i % LINE_COLORS.length],
                  points: a.daily,
                  dashed: true,
                })),
              ]}
            />
            <ul className="mt-2 flex flex-wrap gap-4 text-xs text-muted" aria-label="Lines">
              <li className="flex items-center gap-1.5">
                <span aria-hidden className="inline-block h-0.5 w-5 bg-primary" /> All bank accounts
              </li>
              {(p.accounts ?? []).map((a, i) => (
                <li key={a.account_id} className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="inline-block h-0.5 w-5"
                    style={{ background: LINE_COLORS[i % LINE_COLORS.length] }}
                  />
                  {a.name} (its bills and income only)
                </li>
              ))}
              {(p.band?.length ?? 0) > 1 && <li>Shaded: where cash is in 8 of 10 cases</li>}
              {num(p.floor ?? 0) > 0 && <li>Dashed red: your floor {money(p.floor!)}</li>}
            </ul>
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-muted">The numbers</summary>
              <table className="mt-2 w-full">
                <caption className="sr-only">Projected cash by day</caption>
                <tbody className="divide-y divide-line">
                  {p.daily.map((d, i) => (
                    <tr key={d.day}>
                      <th scope="row" className="py-1 text-left font-normal">
                        {day(d.day)}
                      </th>
                      <td className="num py-1 text-right">{money(d.balance)}</td>
                      {p.band?.[i] && (
                        <td className="num py-1 text-right text-muted">
                          {minus(p.band[i].low)} to {minus(p.band[i].high)}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>

          <h2 className="mt-10 font-display text-2xl font-bold">Spending alerts</h2>
          {p.alerts.length ? (
            <ul
              className="mt-3 divide-y divide-line rounded-2xl border border-line"
              aria-label="Spending alerts"
            >
              {p.alerts.map((a) => (
                <li key={a.group_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                  <span>
                    <strong>{a.group_name}</strong>: <span className="num">{money(a.amount)}</span> in{" "}
                    {monthLong(a.month)},{" "}
                    {a.change != null ? `${Math.round(num(a.change) * 100)}% above` : "above"} its{" "}
                    <span className="num">{money(a.average)}</span> average
                  </span>
                  <Link className="text-primary underline" to={`/spending?month=${a.month.slice(0, 7)}`}>
                    See the spending
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-muted">No category is more than 30% above its recent average.</p>
          )}
        </>
      )}
    </section>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
      {hint && <dd className="text-xs text-muted">{hint}</dd>}
    </div>
  );
}

function Row({
  label,
  months,
  pick,
  strong,
}: {
  label: string;
  months: ProjectionMonth[];
  pick: (m: ProjectionMonth) => string;
  strong?: boolean;
}) {
  return (
    <tr className={strong ? "font-semibold" : ""}>
      <th scope="row" className="px-4 py-2 text-left font-medium">
        {label}
      </th>
      {months.map((m) => (
        <td key={m.month} className="num px-3 py-2 text-right">
          {pick(m)}
        </td>
      ))}
    </tr>
  );
}

const minus = (v: string) => (num(v) < 0 ? `−${money(Math.abs(num(v)))}` : money(v));

/** Why some months ahead are heavier than a usual one (ADR-096). */
function Seasons({ months }: { months: ProjectionMonth[] }) {
  const heavy = months.filter((m) => m.seasonal?.length);
  if (!heavy.length) return null;
  return (
    <ul className="mt-3 space-y-1 text-sm" aria-label="Seasons ahead">
      {heavy.map((m) => (
        <li key={m.month}>
          <strong>{monthLong(m.month)}</strong>:{" "}
          {m
            .seasonal!.map((s) => `${s.group_name} about ${money(s.extra)} more than a usual month`)
            .join("; ")}
          .
        </li>
      ))}
    </ul>
  );
}

/** Accounts that dip under the floor, with how much to move and by when (ADR-033). */
function HeadsUp({ p }: { p: Projection }) {
  const under = (p.accounts ?? []).filter((a) => a.under_floor);
  if (!under.length) return null;
  return (
    <section className="mt-4 rounded-2xl bg-attention-bg px-4 py-3 text-attention-ink" aria-label="Heads-up">
      <p className="text-xs font-semibold tracking-wide uppercase">Heads-up</p>
      <ul className="mt-1 space-y-1">
        {under.map((a) => (
          <li key={a.account_id}>
            <strong>{a.name}</strong> dips to <span className="num">{minus(a.lowest.balance)}</span> on{" "}
            {day(a.lowest.day)}
            {num(p.floor ?? 0) > 0 ? `, under your ${money(p.floor!)} floor` : ""} from {day(a.under_floor!)}.
            Move <strong className="num">{money(a.move)}</strong> in before {day(a.under_floor!)}.
          </li>
        ))}
      </ul>
    </section>
  );
}

function Seg({
  label,
  values,
  value,
  onChange,
}: {
  label: string;
  values: number[];
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <span role="group" aria-label={label} className="inline-flex rounded-lg bg-surface p-0.5 text-sm">
      {values.map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={value === v}
          className={`h-8 rounded-md px-2.5 font-semibold ${value === v ? "bg-ground text-ink" : "text-muted"}`}
          onClick={() => onChange(v)}
        >
          {v}
        </button>
      ))}
    </span>
  );
}

/** How it's calculated, with the choices that change it. */
function Assumptions({
  p,
  opts,
  setOpts,
}: {
  p: Projection;
  opts: ForecastOptions;
  setOpts: (o: Partial<ForecastOptions>) => void;
}) {
  const [floor, setFloor] = useState(String(opts.floor || ""));
  return (
    <section className="card" aria-labelledby="assume">
      <h2 id="assume" className="font-display text-xl font-bold">
        How it’s calculated
      </h2>
      <dl className="mt-3 divide-y divide-line text-sm">
        <div className="flex flex-wrap justify-between gap-2 py-2">
          <dt>
            <strong>Starts from</strong> each bank account’s latest balance
          </dt>
          <dd className="text-muted">
            {p.cash_as_of ? `oldest from ${day(p.cash_as_of)}` : "no statement yet"}
          </dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2 py-2">
          <dt>
            <strong>Income and bills</strong>: your recurring items, on their day; loans from their
            amortization table; purchase installments while they last
          </dt>
          <dd>
            <Link className="text-primary underline" to="/recurring">
              Edit in Bills
            </Link>
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Everyday spending</strong>: {money(p.variable_per_month)} a month, the average of the last
          </dt>
          <dd>
            <Seg
              label="Months to average"
              values={[3, 6, 12]}
              value={opts.average_over}
              onChange={(v) => setOpts({ average_over: v })}
            />
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Seasons</strong>:{" "}
            {!opts.seasons
              ? "every month ahead gets the same average"
              : p.seasonal_groups
                ? `${p.seasonal_groups} ${p.seasonal_groups === 1 ? "group follows" : "groups follow"} their own year (school, December, yearly payments); on cards, paid the month after`
                : "no group shows a pattern yet (it takes two complete years of history)"}
          </dt>
          <dd>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label="Follow the seasons"
                checked={opts.seasons}
                onChange={(e) => setOpts({ seasons: e.target.checked })}
              />
              {opts.seasons ? "yes" : "no"}
            </label>
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Money held for others</strong> ({money(p.held ?? 0)}) counted as yours
          </dt>
          <dd>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={opts.include_held}
                onChange={(e) => setOpts({ include_held: e.target.checked })}
              />
              {opts.include_held ? "yes" : "no"}
            </label>
          </dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 py-2">
          <dt>
            <strong>Floor</strong>: warn when an account goes under
          </dt>
          <dd>
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setOpts({ floor: Math.max(0, Number(floor) || 0) });
              }}
            >
              <label className="sr-only" htmlFor="floor">
                Floor
              </label>
              <input
                id="floor"
                className="field num h-9"
                style={{ width: "7rem" }}
                inputMode="decimal"
                value={floor}
                placeholder="0"
                onChange={(e) => setFloor(e.target.value)}
              />
              <button type="submit" className="btn btn-quiet h-9 px-3">
                Set
              </button>
            </form>
          </dd>
        </div>
      </dl>
    </section>
  );
}

const ONCE_DEFAULT = () => localToday();

/** What if (ADR-033): changes added on top, compared with the forecast without them. */
function WhatIfs({
  changes,
  setChanges,
  p,
}: {
  changes: ForecastChange[];
  setChanges: (c: ForecastChange[]) => void;
  p: Projection;
}) {
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const banks = (accounts.data ?? []).filter((a) => a.kind !== "credit_card" && a.is_active);
  const [kind, setKind] = useState<"move" | "monthly" | "once">("move");
  const [amount, setAmount] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [name, setName] = useState("");
  const [onDay, setOnDay] = useState("1");
  const [onDate, setOnDate] = useState(ONCE_DEFAULT());
  const [direction, setDirection] = useState<"out" | "in">("out");
  const nameOf = (id: string) => banks.find((a) => String(a.account_id) === id)?.name ?? "";
  const add = () => {
    const v = Math.abs(Number(amount));
    if (!v) return;
    if (kind === "move") {
      if (!from || !to || from === to) return;
      const label = `Move ${nameOf(from)} → ${nameOf(to)}`;
      setChanges([
        ...changes,
        {
          name: label,
          amount: String(-v),
          every: "month",
          day: Number(onDay) || 1,
          account_id: Number(from),
        },
        { name: label, amount: String(v), every: "month", day: Number(onDay) || 1, account_id: Number(to) },
      ]);
    } else {
      const signedV = direction === "in" ? v : -v;
      setChanges([
        ...changes,
        {
          name: name.trim() || (kind === "once" ? "One-off" : "Each month"),
          amount: String(signedV),
          every: kind === "once" ? "once" : "month",
          day: Number(onDay) || 1,
          on: kind === "once" ? onDate : null,
          account_id: from ? Number(from) : null,
        },
      ]);
    }
    setAmount("");
    setName("");
  };
  const b = p.base;
  return (
    <section className="card" aria-labelledby="whatif">
      <h2 id="whatif" className="font-display text-xl font-bold">
        What if…
      </h2>
      <div role="group" aria-label="Kind of change" className="mt-3 flex flex-wrap gap-2 text-sm">
        {(
          [
            ["move", "Move money each month"],
            ["monthly", "Something each month"],
            ["once", "A one-off"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            className={`rounded-full border px-3 py-1.5 font-semibold ${kind === k ? "border-primary bg-info-bg" : "border-line"}`}
            onClick={() => setKind(k)}
          >
            {label}
          </button>
        ))}
      </div>
      <form
        className="mt-3 grid gap-2 sm:grid-cols-2"
        aria-label="Add a what-if"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        {kind !== "move" && (
          <>
            <label>
              <span className="label">Name</span>
              <input
                className="field"
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              <span className="label">Money</span>
              <select
                className="field"
                value={direction}
                onChange={(e) => setDirection(e.target.value as "in" | "out")}
              >
                <option value="out">going out</option>
                <option value="in">coming in</option>
              </select>
            </label>
          </>
        )}
        <label>
          <span className="label">Amount</span>
          <input
            className="field num"
            inputMode="decimal"
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        {kind === "once" ? (
          <label>
            <span className="label">On</span>
            <input type="date" className="field" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
          </label>
        ) : (
          <label>
            <span className="label">On day</span>
            <input
              className="field num"
              type="number"
              min={1}
              max={31}
              value={onDay}
              onChange={(e) => setOnDay(e.target.value)}
            />
          </label>
        )}
        <label>
          <span className="label">{kind === "move" ? "From" : "Account (optional)"}</span>
          <select
            className="field"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            required={kind === "move"}
          >
            <option value="">{kind === "move" ? "Choose" : "Any"}</option>
            {banks.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        {kind === "move" && (
          <label>
            <span className="label">To</span>
            <select className="field" value={to} onChange={(e) => setTo(e.target.value)} required>
              <option value="">Choose</option>
              {banks.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="sm:col-span-2">
          <button type="submit" className="btn btn-secondary">
            Add to the forecast
          </button>
        </div>
      </form>
      {changes.length > 0 && (
        <>
          <ul className="mt-3 divide-y divide-line text-sm" aria-label="What-ifs added">
            {changes.map((c, i) => (
              <li key={i} className="flex items-center justify-between gap-2 py-1.5">
                <span>
                  {c.name}: <span className="num">{signedMoney(c.amount)}</span>{" "}
                  {c.every === "once" ? `on ${day(c.on!)}` : `each month on the ${c.day}`}
                </span>
                <button
                  type="button"
                  className="text-sm text-primary underline"
                  onClick={() => setChanges(changes.filter((_, j) => j !== i))}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
          {b && (
            <p className="mt-3 rounded-xl bg-surface px-3 py-2 text-sm" aria-live="polite">
              With these: lowest cash{" "}
              <strong className="num">{p.lowest ? minus(p.lowest.balance) : "—"}</strong> (was{" "}
              <span className="num">{b.lowest ? minus(b.lowest.balance) : "—"}</span>), first day short{" "}
              <strong>{p.first_short ? day(p.first_short) : "none"}</strong> (was{" "}
              {b.first_short ? day(b.first_short) : "none"}), cash at the end{" "}
              <strong className="num">{minus(String(p.end_cash ?? 0))}</strong> (was{" "}
              <span className="num">{minus(b.end_cash)}</span>).
            </p>
          )}
        </>
      )}
    </section>
  );
}
