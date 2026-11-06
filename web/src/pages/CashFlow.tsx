import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { fetchFlowLines, fetchFlows, type Flow, type FlowFilter, type FlowLine, type Flows } from "../api";
import { InOutColumns, Legend, type ColumnDatum } from "../components/charts";
import { Sankey, Waterfall, fold, type SankeyNode, type Step } from "../components/flowcharts";
import { PersonNote, SaveView } from "../components/Personalize";
import { money, monthLong, monthShort, num, showAmount, signed } from "../money";
import { personParam, usePerson, type Person } from "../prefs";
import Overview from "./Overview";

// The Cash flow page (ADR-027): twelve months of money in and out, one month as a Sankey, a
// drill-down from a band to its group, categories, merchants and lines, and why the month
// changed from the one before. The year history (the old Overview) follows below.

const MAX_STEPS = 5;
const PEOPLE_NAMES = ["Hernan", "Lauren", "Joint"];

/** A row of the month: money in by category; money out by group, savings and payments by
 * category (they read better by what they are: Investing, Card Payment). */
export type Row = {
  key: string;
  label: string;
  side: "in" | "out";
  amount: number;
  prev: number;
  color: string | null;
};

export function rows(flows: Flow[]): Row[] {
  const out = new Map<string, Row>();
  for (const f of flows) {
    const side = f.type === "income" ? "in" : "out";
    const byCategory = side === "in" || f.type === "savings" || f.type === "debt_payment";
    const key = `${side}:${byCategory ? `c${f.category_id}` : `g${f.group_id}`}`;
    // "Salary Hernan" rather than "Hernan"; "Office rent" says enough on its own.
    const label = byCategory
      ? PEOPLE_NAMES.includes(f.category_name)
        ? `${f.group_name} ${f.category_name}`
        : f.category_name
      : f.group_name;
    const row = out.get(key) ?? { key, label, side, amount: 0, prev: 0, color: f.group_color };
    row.amount += num(f.amount);
    row.prev += num(f.prev);
    out.set(key, row);
  }
  return [...out.values()];
}

/** What a row opens: its group, or its category. */
export function drillOf(key: string): FlowFilter & { group?: number; category?: number } {
  const [side, id] = key.split(":");
  const n = Number(id.slice(1));
  return id.startsWith("g")
    ? { side: side as "in" | "out", group: n }
    : { side: side as "in" | "out", category: n };
}

/** The biggest changes from the month before, the rest folded into "Everything else". */
export function steps(list: Row[], max = MAX_STEPS): Step[] {
  const changed = list
    .map((r) => ({ key: r.key, label: r.label, change: r.amount - r.prev }))
    .filter((s) => Math.abs(s.change) >= 0.005)
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  if (changed.length <= max) return changed;
  const rest = changed.slice(max - 1).reduce((s, c) => s + c.change, 0);
  return [...changed.slice(0, max - 1), { key: "rest", label: "Everything else", change: rest }];
}

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

function Path({
  f,
  list,
  params,
  set,
}: {
  f: Flows;
  list: Row[];
  params: URLSearchParams;
  set: (patch: Record<string, string | null>, keep?: boolean) => void;
}) {
  const side = params.get("side");
  const g = params.get("g");
  const c = params.get("c");
  const m = params.get("m");
  const flow = (pred: (x: Flow) => boolean) => f.flows.find(pred);
  const steps: { label: string; patch: Record<string, string | null> }[] = [];
  if (side)
    steps.push({ label: side === "in" ? "Money in" : "Money out", patch: { g: null, c: null, m: null } });
  if (g)
    steps.push({
      label: flow((x) => String(x.group_id) === g)?.group_name ?? "Group",
      patch: { c: null, m: null },
    });
  if (c) {
    const row = list.find((r) => r.key === `${side}:c${c}`);
    steps.push({
      label: row?.label ?? flow((x) => String(x.category_id) === c)?.category_name ?? "Category",
      patch: { m: null },
    });
  }
  if (m) steps.push({ label: m, patch: {} });
  return (
    <nav aria-label="Drill path" className="mt-6 flex flex-wrap items-center gap-2 text-sm">
      <button
        type="button"
        className="font-semibold text-primary underline"
        onClick={() => set({ side: null, g: null, c: null, m: null })}
      >
        {monthLong(f.month)}
      </button>
      {steps.map((s, i) => (
        <span key={s.label + i} className="flex items-center gap-2">
          <span aria-hidden className="text-muted">
            ›
          </span>
          {i === steps.length - 1 ? (
            <strong aria-current="location">{s.label}</strong>
          ) : (
            <button
              type="button"
              className="font-semibold text-primary underline"
              onClick={() => set(s.patch)}
            >
              {s.label}
            </button>
          )}
        </span>
      ))}
      {!steps.length && (
        <span className="text-muted">
          Click any bar, band or row to go one level down; the path goes back up.
        </span>
      )}
    </nav>
  );
}

function Why({
  f,
  list,
  params,
  set,
  open,
}: {
  f: Flows;
  list: Row[];
  params: URLSearchParams;
  set: (patch: Record<string, string | null>) => void;
  open: (key: string) => void;
}) {
  const side = params.get("why") === "in" ? "in" : "out";
  const these = list.filter((r) => r.side === side);
  const now = these.reduce((s, r) => s + r.amount, 0);
  const before = these.reduce((s, r) => s + r.prev, 0);
  const st = steps(these);
  const what = side === "in" ? "income" : "spending";
  const word =
    Math.abs(now - before) < 0.005 ? "was the same as" : now > before ? "was higher than" : "was lower than";
  const table = these
    .filter((r) => Math.abs(r.amount - r.prev) >= 0.005)
    .sort((a, b) => Math.abs(b.amount - b.prev) - Math.abs(a.amount - a.prev))
    .slice(0, 8);
  return (
    <section className="card" aria-labelledby="why">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="why" className="font-display text-xl font-bold">
          Why {monthShort(f.month)}’s {what} {word} {monthShort(f.prev_month)}’s
        </h2>
        <div role="group" aria-label="Compare" className="flex rounded-xl bg-surface p-1 text-sm">
          {(["out", "in"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={side === s}
              className={`h-8 rounded-lg px-3 font-semibold ${side === s ? "bg-ground text-ink" : "text-muted"}`}
              onClick={() => set({ why: s === "out" ? null : "in" })}
            >
              {s === "out" ? "Money out" : "Money in"}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4">
        <Waterfall
          from={before}
          to={now}
          steps={st}
          labels={[monthShort(f.prev_month), monthShort(f.month)]}
          upIsGood={side === "in"}
          title={`${what} from ${monthLong(f.prev_month)} ${money(before)} to ${monthLong(f.month)} ${money(now)}, ${st
            .map((s) => `${s.label} ${signed(s.change)}`)
            .join(", ")}`}
        />
      </div>
      {table.length > 0 ? (
        <table className="mt-4 w-full text-sm">
          <caption className="sr-only">Biggest changes</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 text-left font-semibold">
                What changed
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                {monthShort(f.prev_month)}
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                {monthShort(f.month)}
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                Change
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {table.map((r) => (
              <tr key={r.key}>
                <td className="py-1.5">
                  <button
                    type="button"
                    className="text-left text-primary underline"
                    onClick={() => open(r.key)}
                  >
                    {r.label}
                  </button>
                </td>
                <td className="num py-1.5 text-right">{money(r.prev)}</td>
                <td className="num py-1.5 text-right">{money(r.amount)}</td>
                <td className="num py-1.5 text-right">{signed(r.amount - r.prev)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-4 text-sm text-muted">Nothing changed by category.</p>
      )}
    </section>
  );
}

function Drill({
  f,
  list,
  params,
  set,
  person,
}: {
  f: Flows;
  list: Row[];
  params: URLSearchParams;
  set: (patch: Record<string, string | null>) => void;
  person: Person;
}) {
  const side = params.get("side") as "in" | "out" | null;
  const g = params.get("g");
  const c = params.get("c");
  const m = params.get("m");
  const lines = useQuery({
    queryKey: ["cashflow", "lines", f.month, side, c, person],
    queryFn: () =>
      fetchFlowLines(f.month, {
        side: side ?? undefined,
        category_id: Number(c),
        person: personParam(person),
      }),
    enabled: !!side && c !== null,
  });
  if (!side) return null;

  // A side or a group: its categories.
  if (c === null) {
    const cats = f.flows
      .filter((x) => (side === "in" ? x.type === "income" : x.type !== "income"))
      .filter((x) => g === null || String(x.group_id) === g)
      .reduce((acc, x) => {
        const row = acc.get(x.category_id) ?? {
          id: x.category_id,
          name: x.category_name,
          amount: 0,
          prev: 0,
          n: 0,
        };
        row.amount += num(x.amount);
        row.prev += num(x.prev);
        row.n += x.transactions;
        return acc.set(x.category_id, row);
      }, new Map<number, { id: number; name: string; amount: number; prev: number; n: number }>());
    const sorted = [...cats.values()].sort((a, b) => b.amount - a.amount);
    return (
      <Panel
        title={`${g ? (f.flows.find((x) => String(x.group_id) === g)?.group_name ?? "Group") : side === "in" ? "Money in" : "Money out"} by category`}
      >
        <table className="w-full text-sm">
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1 text-left font-semibold">
                Category
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                Lines
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                {monthShort(f.prev_month)}
              </th>
              <th scope="col" className="py-1 text-right font-semibold">
                {monthShort(f.month)}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {sorted.map((r) => (
              <tr key={r.id}>
                <td className="py-1.5">
                  <button
                    type="button"
                    className="text-left text-primary underline"
                    onClick={() => set({ c: String(r.id), m: null })}
                  >
                    {r.name}
                  </button>
                </td>
                <td className="num py-1.5 text-right">{r.n}</td>
                <td className="num py-1.5 text-right">{money(r.prev)}</td>
                <td className="num py-1.5 text-right">{money(r.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    );
  }

  const label =
    list.find((r) => r.key === `${side}:c${c}`)?.label ??
    f.flows.find((x) => String(x.category_id) === c)?.category_name ??
    "Category";
  if (lines.error)
    return (
      <Panel title={label}>
        <p className="text-danger-ink">Could not load the lines: {(lines.error as Error).message}</p>
      </Panel>
    );
  if (!lines.data)
    return (
      <Panel title={label}>
        <p className="text-muted">Loading the lines…</p>
      </Panel>
    );
  const workbook = lines.data.length > 0 && lines.data.every((l) => l.source === "excel_history");

  // A merchant: its lines.
  if (m !== null || workbook) {
    const shown = m === null ? lines.data : lines.data.filter((l) => (l.merchant ?? l.description) === m);
    return (
      <Panel title={m ?? label}>
        {workbook && (
          <p className="mb-3 rounded-2xl bg-info-bg px-4 py-3 text-sm">
            One amount per category from the <strong>Cash Flow workbook</strong>, no statement lines. Upload
            the statements for {monthLong(f.month)} to see the payments, their dates and descriptions here.
          </p>
        )}
        <LineTable lines={shown} />
      </Panel>
    );
  }

  // A category: its merchants.
  const byMerchant = new Map<string, { amount: number; n: number }>();
  for (const l of lines.data) {
    const key = l.merchant ?? l.description;
    const row = byMerchant.get(key) ?? { amount: 0, n: 0 };
    row.amount += side === "in" ? num(l.amount) : -num(l.amount);
    row.n += 1;
    byMerchant.set(key, row);
  }
  const merchants = [...byMerchant.entries()].sort((a, b) => b[1].amount - a[1].amount);
  return (
    <Panel title={`${label} by merchant`}>
      {!merchants.length && <p className="text-muted">No lines.</p>}
      <ul className="divide-y divide-line">
        {merchants.map(([name, r]) => (
          <li key={name} className="flex items-center justify-between gap-3 py-1.5 text-sm">
            <button
              type="button"
              className="text-left text-primary underline"
              onClick={() => set({ m: name })}
            >
              {name}
            </button>
            <span className="num shrink-0">
              {r.n} {r.n === 1 ? "line" : "lines"} · {money(r.amount)}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card mt-6" aria-label={title}>
      <h2 className="mb-3 font-display text-xl font-bold">{title}</h2>
      {children}
    </section>
  );
}

function LineTable({ lines }: { lines: FlowLine[] }) {
  if (!lines.length) return <p className="text-muted">No lines.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-muted">
          <tr>
            <th scope="col" className="py-1 text-left font-semibold">
              Date
            </th>
            <th scope="col" className="py-1 text-left font-semibold">
              Description
            </th>
            <th scope="col" className="py-1 text-left font-semibold">
              Account
            </th>
            <th scope="col" className="py-1 text-left font-semibold">
              Who
            </th>
            <th scope="col" className="py-1 text-right font-semibold">
              Amount
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {lines.map((l) => (
            <tr key={l.transaction_id}>
              <td className="num whitespace-nowrap py-1.5">{l.txn_date}</td>
              <td className="py-1.5">
                {l.description}
                {l.notes && <span className="block text-xs text-muted">{l.notes}</span>}
              </td>
              <td className="py-1.5 text-muted">
                {l.account_name ?? (l.source === "excel_history" ? "Workbook" : "")}
              </td>
              <td className="py-1.5">{l.person}</td>
              <td className="num py-1.5 text-right">{showAmount(l.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
