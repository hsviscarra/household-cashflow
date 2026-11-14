import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchFlows, type Flows } from "../api";
import { InOutColumns, Legend, type ColumnDatum } from "../components/charts";
import { Sankey, fold, type SankeyNode } from "../components/flowcharts";
import { PersonNote, SaveView } from "../components/Personalize";
import { money, monthLong, monthShort, num } from "../money";
import { personParam, usePerson, type Person } from "../prefs";
import Overview from "./Overview";
import { type Row, rows, drillOf } from "./cashflow/shared";
import { Path, Why } from "./cashflow/Explain";
import { Drill } from "./cashflow/Drill";

export { type Row, rows, drillOf, steps } from "./cashflow/shared";

export default function CashFlowPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? `${raw}-01` : null;
  const [person, , ready] = usePerson();
  const q = useQuery({
    queryKey: ["cashflow", "flows", month, person],
    queryFn: () => fetchFlows(month, personParam(person)),
    enabled: ready,
  });
  const set = (patch: Record<string, string | null>, keep = true) => {
    const next = new URLSearchParams(keep ? params : undefined);
    if (!keep && params.get("month")) next.set("month", params.get("month")!);
    Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)));
    setParams(next);
  };
  const f = q.data;

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-4xl font-bold leading-tight">Cash flow</h1>
        <SaveView month={f ? monthLong(f.month) : undefined} />
      </div>
      <PersonNote person={person} />
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the cash flow: {(q.error as Error).message}
        </p>
      )}
      {!f && !q.error && <p className="mt-6 text-muted">Adding up the months…</p>}
      {f && f.source === "none" && !f.months.length && (
        <p className="mt-6 rounded-2xl bg-info-bg px-5 py-4">
          Nothing loaded yet.{" "}
          <Link className="text-primary underline" to="/import">
            Load the Excel history or upload statements
          </Link>
          .
        </p>
      )}
      {f && f.months.length > 0 && <Month f={f} params={params} set={set} person={person} />}
      {f && (f.months.length > 0 || person !== "Both") && (
        <div className="mt-10">
          <Overview />
        </div>
      )}
    </section>
  );
}

function Month({
  f,
  params,
  set,
  person,
}: {
  f: Flows;
  params: URLSearchParams;
  set: (patch: Record<string, string | null>, keep?: boolean) => void;
  person: Person;
}) {
  const list = rows(f.flows);
  const money_in = list.filter((r) => r.side === "in").reduce((s, r) => s + r.amount, 0);
  const money_out = list.filter((r) => r.side === "out").reduce((s, r) => s + r.amount, 0);
  const kept = money_in - money_out;
  const columns: ColumnDatum[] = f.trend.map((t) => ({
    key: t.month,
    label: monthShort(t.month),
    in: num(t.money_in),
    out: num(t.money_out),
    selected: t.month === f.month,
    tooltip: (
      <>
        <div className="font-semibold">{monthLong(t.month)}</div>
        <div className="num flex justify-between">
          <span>In</span>
          <span>{money(t.money_in)}</span>
        </div>
        <div className="num flex justify-between">
          <span>Out</span>
          <span>{money(t.money_out)}</span>
        </div>
      </>
    ),
  }));
  const node = (r: Row): SankeyNode => ({
    key: r.key,
    label: r.label,
    amount: r.amount,
    color: r.side === "out" ? r.color : null,
  });
  const left = fold(list.filter((r) => r.side === "in").map(node), "Other income");
  const right = fold(list.filter((r) => r.side === "out").map(node), "Other");
  if (kept < 0)
    left.push({ key: "gap", label: "From savings", amount: -kept, color: "var(--color-muted)", fixed: true });
  if (kept > 0)
    right.push({ key: "kept", label: "Left over", amount: kept, color: "var(--color-flow-in)", fixed: true });
  const open = (key: string) => {
    const d = drillOf(key);
    set({
      side: d.side ?? null,
      g: d.group !== undefined ? String(d.group) : null,
      c: d.category !== undefined ? String(d.category) : null,
      m: null,
    });
  };

  return (
    <>
      <section className="card mt-6" aria-labelledby="trend">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 id="trend" className="font-display text-xl font-bold">
            Money in and out, month by month
          </h2>
          <Legend
            items={[
              { label: "Money in", color: "var(--color-flow-in)" },
              { label: "Money out", color: "var(--color-flow-out)" },
            ]}
          />
        </div>
        <div className="mt-4 overflow-hidden">
          <InOutColumns
            data={columns}
            title={`Money in and out, the twelve months to ${monthLong(f.month)}`}
            onSelect={(m) => set({ month: m.slice(0, 7), side: null, g: null, c: null, m: null })}
          />
        </div>
        <p className="mt-2 text-sm text-muted">Pick a month to see where its money came from and went.</p>
      </section>

      <Path f={f} list={list} params={params} set={set} />

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="card" aria-labelledby="sankey">
          <h2 id="sankey" className="font-display text-xl font-bold">
            {monthLong(f.month)}: where <span className="num">{money(money_in)}</span> came from and went
          </h2>
          <p className="mt-1 text-sm text-muted">
            {kept >= 0 ? (
              <>
                Kept <span className="num">{money(kept)}</span>.
              </>
            ) : (
              <>
                <span className="num">{money(-kept)}</span> more went out than came in.
              </>
            )}{" "}
            {f.source === "excel" ? "From the Cash Flow workbook." : "From approved statements."} Click a band
            to open it.
          </p>
          <div className="mt-4">
            <Sankey
              left={left}
              right={right}
              middle={monthShort(f.month)}
              title={`Where the money of ${monthLong(f.month)} came from and went`}
              onSelect={(_, key) => open(key)}
            />
          </div>
        </section>
        <Why f={f} list={list} params={params} set={set} open={open} />
      </div>

      <Drill f={f} list={list} params={params} set={set} person={person} />
    </>
  );
}
