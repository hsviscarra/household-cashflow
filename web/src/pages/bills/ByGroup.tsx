import { type Bill } from "../../api";
import { useState, Fragment } from "react";
import { monthShort, money, num, monthLong, pct } from "../../money";
import { size, repeats, STATUS } from "./shared";

export function ByGroup({ bills, month }: { bills: Bill[]; month: string }) {
  const groups = [...new Set(bills.map((b) => b.group || "Other"))];
  const [open, setOpen] = useState<Set<string>>(new Set(groups.slice(0, 1)));
  const sum = (bs: Bill[], f: (b: Bill) => number) => bs.reduce((s, b) => s + f(b), 0);
  return (
    <section className="card mt-6 overflow-x-auto" aria-labelledby="by-group">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="by-group" className="font-display text-xl font-bold">
          By group, with each item inside
        </h2>
        <span className="text-sm text-muted">Open a group to see its items; edit them on the Year grid.</span>
      </div>
      <table className="mt-3 w-full text-sm">
        <thead className="text-muted">
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Item
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Paid from
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Repeats
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              {monthShort(`${month}-01`)}
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              Last 3 months avg
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {groups.map((g) => {
            const items = bills.filter((b) => (b.group || "Other") === g);
            const lateN = items.filter((b) => b.status === "late").length;
            const changed = items.filter((b) => b.price_from).length;
            const isOpen = open.has(g);
            return (
              <Fragment key={g}>
                <tr className="bg-surface font-semibold">
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() =>
                        setOpen((o) => {
                          const n = new Set(o);
                          if (n.has(g)) n.delete(g);
                          else n.add(g);
                          return n;
                        })
                      }
                    >
                      <span aria-hidden>{isOpen ? "▾" : "▸"}</span> {g}
                    </button>
                  </td>
                  <td />
                  <td className="px-2 py-1.5 font-normal text-muted">
                    {items.length} {items.length === 1 ? "item" : "items"}
                  </td>
                  <td className="num px-2 py-1.5 text-right">{money(sum(items, size))}</td>
                  <td className="num px-2 py-1.5 text-right">
                    {money(sum(items, (b) => Math.abs(num(b.avg3))))}
                  </td>
                  <td className="px-2 py-1.5 font-normal">
                    {lateN > 0 && (
                      <span className="rounded-md bg-danger-bg px-1.5 py-0.5 text-xs text-danger-ink">
                        {lateN} late
                      </span>
                    )}{" "}
                    {changed > 0 && (
                      <span className="rounded-md bg-attention-bg px-1.5 py-0.5 text-xs text-attention-ink">
                        {changed} price {changed === 1 ? "change" : "changes"}
                      </span>
                    )}
                  </td>
                </tr>
                {isOpen &&
                  items.map((b) => (
                    <tr key={b.template_id}>
                      <td className="px-2 py-1.5 pl-6">{b.name}</td>
                      <td className="px-2 py-1.5 text-muted">{b.account_name ?? "Any account"}</td>
                      <td className="px-2 py-1.5 text-muted">{repeats(b)}</td>
                      <td className="num px-2 py-1.5 text-right">{money(size(b))}</td>
                      <td className="num px-2 py-1.5 text-right">
                        {b.avg3 ? money(Math.abs(num(b.avg3))) : "—"}
                      </td>
                      <td className="px-2 py-1.5">
                        <span
                          className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${STATUS[b.status].cls}`}
                        >
                          {STATUS[b.status].label}
                          {b.status !== "paid" && b.due_day
                            ? ` ${monthShort(`${month}-01`)} ${b.due_day}`
                            : ""}
                        </span>
                      </td>
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export function Prices({ bills }: { bills: Bill[] }) {
  const changed = bills.filter((b) => b.price_from && b.price_changed);
  return (
    <section className="card mt-6" aria-labelledby="prices">
      <h2 id="prices" className="font-display text-xl font-bold">
        Price changes in the last six months
      </h2>
      {!changed.length && <p className="mt-2 text-muted">No item changed its amount lately.</p>}
      <ul className="mt-3 divide-y divide-line">
        {changed.map((b) => {
          const was = Math.abs(num(b.price_from));
          const now = Math.abs(num(b.expected));
          const up = now > was;
          return (
            <li key={b.template_id} className="flex flex-wrap items-baseline justify-between gap-3 py-2">
              <span>
                <strong>{b.name}</strong>
                <span className="text-muted"> · from {monthLong(b.price_changed!)}</span>
              </span>
              <span className="num">
                {money(was)} → {money(now)}{" "}
                <span className={up ? "text-danger-ink" : "text-good-ink"}>
                  ({up ? "+" : "−"}
                  {pct(Math.abs(now - was) / (was || 1))})
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
