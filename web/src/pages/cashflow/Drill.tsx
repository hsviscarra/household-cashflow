import { type Flows, fetchFlowLines, type FlowLine } from "../../api";
import { type Row } from "./shared";
import { type Person, personParam } from "../../prefs";
import { useQuery } from "@tanstack/react-query";
import { num, monthShort, money, monthLong, showAmount } from "../../money";

export function Drill({
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

export function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card mt-6" aria-label={title}>
      <h2 className="mb-3 font-display text-xl font-bold">{title}</h2>
      {children}
    </section>
  );
}

export function LineTable({ lines }: { lines: FlowLine[] }) {
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
