import { type GroceryTrends } from "../../api";
import { useState, useMemo } from "react";
import { addMonths, num, monthLong, monthShort, money } from "../../money";
import { type Dim, NO_LABEL, DIMS, signedPct } from "./shared";

/** Any two months side by side, by aisle, type of product or brand. */
export function Compare({ t, month }: { t: GroceryTrends; month: string }) {
  const list = t.months.map((m) => m.month.slice(0, 7));
  const [b, setB] = useState(list.includes(month) ? month : list[list.length - 1]);
  const [a, setA] = useState(addMonths(`${b}-01`, -1).slice(0, 7));
  const [dim, setDim] = useState<Dim>("aisle");
  const rows = useMemo(() => {
    const by = new Map<string, [number, number]>();
    for (const c of t.cells) {
      const m = c.month.slice(0, 7);
      if (m !== a && m !== b) continue;
      const name = (dim === "aisle" ? c.aisle : c[dim]) ?? NO_LABEL[dim];
      const r = by.get(name) ?? [0, 0];
      if (m === a) r[0] += num(c.amount);
      if (m === b) r[1] += num(c.amount);
      by.set(name, r);
    }
    return [...by.entries()]
      .map(([name, [x, y]]) => ({ name, a: x, b: y, d: y - x }))
      .sort((p, q) => Math.abs(q.d) - Math.abs(p.d));
  }, [t.cells, a, b, dim]);
  const total = rows.reduce((s, r) => [s[0] + r.a, s[1] + r.b], [0, 0]);
  const maxD = Math.max(1, ...rows.map((r) => Math.abs(r.d)));
  const pick = (label: string, value: string, on: (v: string) => void) => (
    <label>
      <span className="label">{label}</span>
      <select className="field w-44" value={value} onChange={(e) => on(e.target.value)}>
        {list.map((m) => (
          <option key={m} value={m}>
            {monthLong(`${m}-01`)}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <section aria-labelledby="compare" className="card space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="compare" className="font-display text-xl font-bold">
            Compare two months
          </h2>
          <p className="text-sm text-muted">From the invoices; biggest change first.</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {pick("Month A", a, setA)}
          {pick("Month B", b, setB)}
          <div
            role="radiogroup"
            aria-label="Compare by"
            className="flex rounded-[10px] bg-surface p-1 text-sm"
          >
            {DIMS.map(([d, name]) => (
              <button
                key={d}
                role="radio"
                aria-checked={dim === d}
                onClick={() => setDim(d)}
                className={`rounded-lg px-3 py-1.5 font-semibold ${dim === d ? "bg-ground shadow-sm" : "text-muted"}`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No supermarket invoices in either month.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted">
              <tr>
                <th scope="col" className="px-2 py-1 text-left font-semibold">
                  {DIMS.find(([d]) => d === dim)![1]}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  {monthShort(`${a}-01`)} {a.slice(0, 4)}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  {monthShort(`${b}-01`)} {b.slice(0, 4)}
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Change
                </th>
                <th scope="col" className="hidden w-48 px-2 py-1 sm:table-cell">
                  <span className="sr-only">Change, drawn</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.slice(0, 25).map((r) => (
                <tr key={r.name}>
                  <td className="max-w-64 truncate px-2 py-1.5" title={r.name}>
                    {r.name}
                  </td>
                  <td className="num px-2 py-1.5 text-right">{money(r.a)}</td>
                  <td className="num px-2 py-1.5 text-right">{money(r.b)}</td>
                  <td
                    className={`num px-2 py-1.5 text-right ${r.d > 0.005 ? "text-danger-ink" : r.d < -0.005 ? "text-good-ink" : "text-muted"}`}
                  >
                    {r.d > 0 ? "+" : ""}
                    {money(r.d)}
                    {r.a > 0 && <span className="block text-xs">{signedPct(r.d / r.a)}</span>}
                    {r.a === 0 && r.b > 0 && <span className="block text-xs">new</span>}
                  </td>
                  <td className="hidden px-2 py-1.5 sm:table-cell">
                    <div className="relative h-2.5">
                      <span aria-hidden className="absolute inset-y-0 left-1/2 w-px bg-line" />
                      <span
                        aria-hidden
                        className={`absolute inset-y-0 rounded-sm ${r.d >= 0 ? "left-1/2 bg-danger-ink" : "right-1/2 bg-good-ink"}`}
                        style={{ width: `${(Math.abs(r.d) / maxD) * 50}%` }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-line font-semibold">
              <tr>
                <td className="px-2 py-1.5">Total</td>
                <td className="num px-2 py-1.5 text-right">{money(total[0])}</td>
                <td className="num px-2 py-1.5 text-right">{money(total[1])}</td>
                <td className="num px-2 py-1.5 text-right">
                  {total[1] - total[0] > 0 ? "+" : ""}
                  {money(total[1] - total[0])}
                </td>
                <td className="hidden sm:table-cell" />
              </tr>
            </tfoot>
          </table>
          {rows.length > 25 && (
            <p className="mt-2 text-xs text-muted">The 25 biggest changes of {rows.length}.</p>
          )}
        </div>
      )}
    </section>
  );
}

/** This month's aisles against their average of the three months before. */
export function VsUsual({ t, month }: { t: GroceryTrends; month: string }) {
  const i = t.months.findIndex((m) => m.month.slice(0, 7) === month);
  const before = i > 0 ? t.months.slice(Math.max(0, i - 3), i).filter((m) => m.trips > 0) : [];
  const now = i >= 0 ? t.months[i] : null;
  const rows =
    now && before.length
      ? t.aisles
          .map((a) => {
            const usual = before.reduce((s, m) => s + num(m.aisles[a]), 0) / before.length;
            const v = num(now.aisles[a]);
            return { a, v, usual, d: v - usual };
          })
          .filter((r) => Math.abs(r.d) >= 1)
          .sort((p, q) => Math.abs(q.d) - Math.abs(p.d))
          .slice(0, 6)
      : [];
  return (
    <section aria-labelledby="vs-usual" className="card space-y-3 p-5">
      <div>
        <h2 id="vs-usual" className="font-display text-xl font-bold">
          {now ? monthLong(now.month) : "This month"} against your usual
        </h2>
        <p className="text-sm text-muted">Each aisle against its average of the 3 months before.</p>
      </div>
      {rows.length === 0 && (
        <p className="text-sm text-muted">Not enough months with invoices to compare yet.</p>
      )}
      <ul className="divide-y divide-line text-sm">
        {rows.map((r) => (
          <li key={r.a} className="flex items-baseline justify-between gap-3 py-2">
            <span className="min-w-0 truncate">
              {r.a}
              <span className="block text-xs text-muted">
                {money(r.v)} · usual {money(r.usual)}
              </span>
            </span>
            <span className={`num shrink-0 font-semibold ${r.d > 0 ? "text-danger-ink" : "text-good-ink"}`}>
              {r.d > 0 ? "+" : "−"}
              {money(Math.abs(r.d))}
              {r.usual > 0 && (
                <span className="block text-right text-xs font-normal">{signedPct(r.d / r.usual)}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
