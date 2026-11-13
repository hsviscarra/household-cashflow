import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DEFAULT_AHEAD, fetchAhead, type Ahead, type AheadChoices } from "../api";
import ChartTools from "../components/ChartTools";
import { Legend, StackedColumns } from "../components/charts";
import { money, num } from "../money";
import { asRecord, useSettings } from "../prefs";

// Net worth five to ten years ahead (ADR-098, plan item C4): what you keep a year pays the
// loans and builds cash or investments; investments grow at a low, an expected and a high
// return. Arithmetic on the assumptions shown, in today's money.

export type Milestone = { name: string; date: string };
const CHOICES_KEY = "long-view";
const MILESTONES_KEY = "long-view:milestones";
const MAX_MILESTONES = 30;
const PARTS = [
  { key: "cash", label: "Cash", color: "var(--color-flow-in)" },
  { key: "investments", label: "Investments (expected)", color: "var(--color-primary)" },
  { key: "property", label: "Property", color: "var(--color-cat-services)" },
  { key: "vehicles", label: "Vehicles", color: "var(--color-cat-transport)" },
  { key: "other_assets", label: "Other", color: "var(--color-cat-fixed)" },
] as const;
// The rates a person may type, as the server accepts them (fractions).
const RATE_MIN = -0.5;
const RATE_MAX = 0.5;

const minus = (v: string | number) => (num(v) < 0 ? `−${money(Math.abs(num(v)))}` : money(v));
const within = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** The saved choices, with anything unreadable replaced by the default and the returns in order. */
export function choices(saved: unknown): AheadChoices {
  const s = asRecord(saved);
  const rate = (k: keyof AheadChoices, lo = RATE_MIN, hi = RATE_MAX) =>
    typeof s[k] === "number" && Number.isFinite(s[k]) ? within(s[k] as number, lo, hi) : DEFAULT_AHEAD[k];
  const [low, expected, high] = [rate("low"), rate("expected"), rate("high")].sort((a, b) => a - b);
  return {
    years: s.years === 10 ? 10 : 5,
    low,
    expected,
    high,
    property_growth: rate("property_growth"),
    vehicle_growth: rate("vehicle_growth"),
    invest_share: rate("invest_share", 0, 1),
  };
}

export function milestonesOf(saved: unknown): Milestone[] {
  if (!Array.isArray(saved)) return [];
  return saved.filter(
    (m): m is Milestone =>
      typeof m === "object" &&
      m !== null &&
      typeof m.name === "string" &&
      typeof m.date === "string" &&
      /^\d{4}-\d{2}-\d{2}$/.test(m.date),
  );
}

/** "In 2031 your net worth is about 310,000.00 (between 295,000.00 and 327,000.00), 120,000.00 more than today." */
export function aheadHeadline(a: Ahead): string {
  const last = a.years[a.years.length - 1];
  if (!last) return "Years ahead";
  const more = num(last.net) - num(a.net_today);
  const range =
    last.net_low === last.net_high ? "" : ` (between ${minus(last.net_low)} and ${minus(last.net_high)})`;
  return `In ${last.year} your net worth is about ${minus(last.net)}${range}, ${money(Math.abs(more))} ${more >= 0 ? "more" : "less"} than today`;
}

export default function NetWorthAheadPage() {
  const { settings, set } = useSettings();
  const c = choices(settings[CHOICES_KEY]);
  const mine = milestonesOf(settings[MILESTONES_KEY]);
  const change = (part: Partial<AheadChoices>) => set(CHOICES_KEY, { ...c, ...part });
  const q = useQuery({
    queryKey: ["networth", "ahead", c],
    queryFn: () => fetchAhead(c),
    placeholderData: (old) => old,
  });
  const a = q.data;
  const notes = (year: number, known: string[]) => [
    ...known,
    ...mine.filter((m) => Number(m.date.slice(0, 4)) === year).map((m) => m.name),
  ];
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {a ? aheadHeadline(a) : "Years ahead"}
      </h1>
      <p className="mt-2 max-w-3xl text-lg text-muted">
        If you keep what you kept in the last twelve months, the loans follow their tables and investments
        grow at the returns you choose. In today’s money; arithmetic on these assumptions, not a prediction.
      </p>
      <Choices c={c} change={change} />
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the years ahead: {(q.error as Error).message}
        </p>
      )}
      {!a && !q.error && <p className="mt-6 text-muted">Adding up the years…</p>}
      {a && (
        <>
          <p className="mt-4 text-muted" aria-label="What it starts from">
            Starts from a net worth of <strong className="num text-ink">{minus(a.net_today)}</strong> today
            and <strong className="num text-ink">{money(a.kept_a_year)}</strong> kept a year (money in less
            spent).
            {a.loans.some((l) => !l.from_table) &&
              ` Without an amortization table, no interest is counted for: ${a.loans
                .filter((l) => !l.from_table)
                .map((l) => l.name)
                .join(", ")}.`}
          </p>
          <div className="mt-4 flex justify-end">
            <ChartTools
              name="Years ahead"
              csv={{
                file: "net-worth-years-ahead.csv",
                rows: () => [
                  [
                    "Year",
                    "Kept",
                    "Cash",
                    "Investments",
                    "Property",
                    "Vehicles",
                    "Owed",
                    "Net worth",
                    "Low",
                    "High",
                  ],
                  ...a.years.map((y) => [
                    y.year,
                    y.kept,
                    y.cash,
                    y.investments,
                    y.property,
                    y.vehicles,
                    (num(y.loans) + num(y.other_debts)).toFixed(2),
                    y.net,
                    y.net_low,
                    y.net_high,
                  ]),
                ],
              }}
              explain={`Explain the net worth projection for the next ${c.years} years: what grows it most and which assumption matters most.`}
            />
          </div>
          <div className="mt-2 rounded-2xl bg-surface p-4 md:p-6">
            <StackedColumns
              title={`What you own by year, and net worth as a line, ${a.years[0].year} to ${a.years[a.years.length - 1].year}`}
              data={a.years.map((y) => ({
                key: String(y.year),
                label: String(y.year),
                line: num(y.net),
                segments: PARTS.map((p) => ({ key: p.key, color: p.color, value: num(y[p.key]) })),
                tooltip: (
                  <>
                    <strong>End of {y.year}</strong>
                    {PARTS.filter((p) => num(y[p.key]) !== 0).map((p) => (
                      <span key={p.key} className="num block">
                        {p.label} {minus(y[p.key])}
                      </span>
                    ))}
                    {num(y.loans) + num(y.other_debts) > 0 && (
                      <span className="num block">Owed −{money(num(y.loans) + num(y.other_debts))}</span>
                    )}
                    <span className="num block font-semibold">Net worth {minus(y.net)}</span>
                    {notes(y.year, y.milestones).map((m) => (
                      <span key={m} className="block text-muted">
                        {m}
                      </span>
                    ))}
                  </>
                ),
              }))}
            />
            <Legend
              items={[
                ...PARTS.map((p) => ({ label: p.label, color: p.color })),
                { label: "Net worth (line)", color: "var(--color-ink)" },
              ]}
            />
          </div>
          <div className="mt-6 overflow-x-auto rounded-2xl border border-line">
            <table className="w-full text-sm">
              <caption className="sr-only">Net worth by year</caption>
              <thead className="bg-surface text-muted">
                <tr>
                  {[
                    "End of",
                    "Kept in the year",
                    "Cash",
                    "Investments",
                    "Property and vehicles",
                    "Owed",
                    "Net worth",
                    "Low to high",
                    "Milestones",
                  ].map((h, i) => (
                    <th
                      key={h}
                      scope="col"
                      className={`px-3 py-2 font-semibold ${i > 0 && i < 8 ? "text-right" : "text-left"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {a.years.map((y) => (
                  <tr key={y.year}>
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      {y.year}
                    </th>
                    <td className="num px-3 py-2 text-right">{minus(y.kept)}</td>
                    <td className="num px-3 py-2 text-right">{minus(y.cash)}</td>
                    <td className="num px-3 py-2 text-right">{money(y.investments)}</td>
                    <td className="num px-3 py-2 text-right">
                      {money(num(y.property) + num(y.vehicles) + num(y.other_assets))}
                    </td>
                    <td className="num px-3 py-2 text-right">{money(num(y.loans) + num(y.other_debts))}</td>
                    <td className="num px-3 py-2 text-right font-semibold">{minus(y.net)}</td>
                    <td className="num px-3 py-2 text-right text-muted">
                      {minus(y.net_low)} to {minus(y.net_high)}
                    </td>
                    <td className="px-3 py-2">{notes(y.year, y.milestones).join(" · ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Milestones mine={mine} save={(list) => set(MILESTONES_KEY, list)} />
        </>
      )}
    </section>
  );
}

/** A rate typed as a percent, kept as a fraction once it leaves the box. */
function Percent({
  label,
  value,
  onChange,
  min = RATE_MIN,
  max = RATE_MAX,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
}) {
  const shown = String(Number((value * 100).toFixed(2)));
  const [typed, setTyped] = useState(shown);
  const [was, setWas] = useState(shown);
  if (shown !== was) {
    setWas(shown);
    setTyped(shown);
  }
  const commit = () => {
    const v = Number(typed);
    if (typed.trim() === "" || !Number.isFinite(v)) setTyped(shown);
    else onChange(within(v / 100, min, max));
  };
  return (
    <label>
      <span className="label">{label}</span>
      <input
        className="field num !w-28"
        inputMode="decimal"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
    </label>
  );
}

function Choices({ c, change }: { c: AheadChoices; change: (part: Partial<AheadChoices>) => void }) {
  return (
    <div className="mt-4 flex flex-wrap items-end gap-3" role="group" aria-label="Assumptions">
      <div role="group" aria-label="Years ahead" className="inline-flex rounded-xl bg-surface p-1 text-sm">
        {[5, 10].map((n) => (
          <button
            key={n}
            type="button"
            aria-pressed={c.years === n}
            className={`h-9 rounded-lg px-3 font-semibold ${c.years === n ? "bg-ground text-ink shadow-sm" : "text-muted"}`}
            onClick={() => change({ years: n })}
          >
            {n} years
          </button>
        ))}
      </div>
      <Percent label="Return, low %" value={c.low} onChange={(low) => change({ low })} />
      <Percent label="Return, expected %" value={c.expected} onChange={(expected) => change({ expected })} />
      <Percent label="Return, high %" value={c.high} onChange={(high) => change({ high })} />
      <Percent
        label="Property a year %"
        value={c.property_growth}
        onChange={(property_growth) => change({ property_growth })}
      />
      <Percent
        label="Vehicles a year %"
        value={c.vehicle_growth}
        onChange={(vehicle_growth) => change({ vehicle_growth })}
      />
      <Percent
        label="Invested of what is free %"
        value={c.invest_share}
        min={0}
        max={1}
        onChange={(invest_share) => change({ invest_share })}
      />
    </div>
  );
}

/** Dates of your own (a school stage, a move): shown in their year. Loans and goals add theirs. */
function Milestones({ mine, save }: { mine: Milestone[]; save: (list: Milestone[]) => void }) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  return (
    <section className="card mt-6" aria-labelledby="milestones">
      <h2 id="milestones" className="font-display text-xl font-bold">
        Your milestones
      </h2>
      <p className="mt-1 text-sm text-muted">
        A loan’s last installment and each goal’s date are added on their own. Add the ones only you know.
      </p>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim() || !date) return;
          save(
            [...mine, { name: name.trim(), date }]
              .sort((x, y) => x.date.localeCompare(y.date))
              .slice(0, MAX_MILESTONES),
          );
          setName("");
          setDate("");
        }}
      >
        <label>
          <span className="label">Milestone</span>
          <input
            className="field !w-64"
            maxLength={60}
            placeholder="High school starts"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          <span className="label">Date</span>
          <input type="date" className="field" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={!name.trim() || !date}>
          Add milestone
        </button>
      </form>
      {mine.length > 0 && (
        <ul className="mt-3 divide-y divide-line text-sm" aria-label="Your milestones">
          {mine.map((m) => (
            <li key={`${m.date}-${m.name}`} className="flex items-center justify-between gap-2 py-1.5">
              <span>
                <span className="num text-muted">{m.date.slice(0, 7)}</span> · {m.name}
              </span>
              <button
                type="button"
                className="text-primary underline"
                aria-label={`Remove ${m.name}`}
                onClick={() => save(mine.filter((x) => x !== m))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
