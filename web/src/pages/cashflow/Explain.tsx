import { type Flows, type Flow } from "../../api";
import { type Row, steps } from "./shared";
import { monthLong, monthShort, money, signed } from "../../money";
import { Waterfall } from "../../components/flowcharts";

export function Path({
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

export function Why({
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
