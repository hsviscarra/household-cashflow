import { type MonthMeasures, fetchMeasures, fetchPortfolio, fetchBudget } from "../../api";
import { useSettings, usePerson, asRecord, personParam } from "../../prefs";
import { useQuery } from "@tanstack/react-query";
import { monthEnd, day, Card } from "./shared";
import { monthShort, num, monthLong, money, localToday } from "../../money";
import { useSearchParams, Link } from "react-router-dom";
import ChartTools from "../../components/ChartTools";
import { StackedColumns, Legend } from "../../components/charts";

export const FLOW_PERIODS = { "6": "6 months", "12": "12 months", "24": "24 months" };

export type FlowPeriod = keyof typeof FLOW_PERIODS;

/** Money in, spent and set aside by month, over a period the person chooses (ADR-101). The page's
 * measures cover 12 months; any other period is asked for. */
export function CashFlow12({ m: twelve }: { m: MonthMeasures }) {
  const { settings, set } = useSettings();
  const [person] = usePerson();
  const saved = String(asRecord(settings["chart:home-cashflow"]).period);
  const period: FlowPeriod = saved in FLOW_PERIODS ? (saved as FlowPeriod) : "12";
  const other = useQuery({
    queryKey: ["cashflow", "measures", twelve.month, person, period],
    queryFn: () => fetchMeasures(twelve.month, personParam(person), Number(period)),
    enabled: period !== "12",
  });
  const m = period === "12" ? twelve : (other.data ?? twelve);
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
      title={`Cash flow, ${period} months`}
      link={[`/cashflow?month=${m.month.slice(0, 7)}`, "Cash flow"]}
    >
      <div className="mb-2">
        <ChartTools
          name="Cash flow"
          period={{
            value: period,
            options: FLOW_PERIODS,
            onChange: (p) => set("chart:home-cashflow", { period: p }),
          }}
          csv={{
            file: "cash-flow.csv",
            rows: () => [
              ["Month", "Money in", "Spent", "Set aside", "Left over"],
              ...m.months.map((p) => [
                p.month.slice(0, 7),
                num(p.money_in).toFixed(2),
                num(p.spent).toFixed(2),
                num(p.set_aside).toFixed(2),
                num(p.left_over).toFixed(2),
              ]),
            ],
          }}
          explain={`Explain our cash flow over the last ${period} months: what came in, what was spent and set aside, and which months stand out.`}
        />
      </div>
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

export function Investments() {
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

export const BUDGET_TONE: Record<string, string> = {
  over: "bg-danger-ink",
  ahead: "bg-attention-ink",
  on_track: "bg-flow-in",
  none: "bg-line",
};

export function Budget({ month }: { month: string }) {
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
