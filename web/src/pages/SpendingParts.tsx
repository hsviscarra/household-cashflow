// Spending, one level deeper (ADR-028): the views (groups as a treemap, merchants, products,
// fixed or variable), the merchants and products tables, and ways to save.
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchIdeas, fetchMerchants, fetchProducts, type Spending } from "../api";
import Treemap from "../components/Treemap";
import { money, monthLong, num, pct } from "../money";

export const VIEWS = {
  groups: "Groups",
  merchants: "Merchants",
  products: "Products",
  fixed: "Fixed vs variable",
};
export type View = keyof typeof VIEWS;

export function ViewSwitch({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  return (
    <div role="group" aria-label="Look at" className="flex flex-wrap rounded-xl bg-surface p-1 text-sm">
      {(Object.keys(VIEWS) as View[]).map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={view === v}
          className={`h-9 rounded-lg px-3 font-semibold ${view === v ? "bg-ground text-ink shadow-sm" : "text-muted"}`}
          onClick={() => onChange(v)}
        >
          {VIEWS[v]}
        </button>
      ))}
    </div>
  );
}

/** The month's groups as blocks; a click goes inside the group. */
export function GroupMap({ s, onPick }: { s: Spending; onPick: (groupId: number) => void }) {
  return (
    <section className="card mt-6" aria-labelledby="map">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="map" className="font-display text-xl font-bold">
          Where {monthLong(s.month)} went
        </h2>
        <span className="text-sm text-muted">Block size = amount. Click a block to go inside.</span>
      </div>
      <div className="mt-4">
        <Treemap
          title={`Spending by group, ${monthLong(s.month)}`}
          items={s.groups.map((g) => ({
            key: String(g.group_id),
            label: g.name,
            amount: num(g.amount),
            color: g.color,
            note: `${g.transactions} ${g.transactions === 1 ? "line" : "lines"}`,
          }))}
          onSelect={(k) => onPick(Number(k))}
        />
      </div>
    </section>
  );
}

/** Merchants with visits, average ticket and invoices; a click opens the merchant's lines. */
export function MerchantTable({
  month,
  person,
  groupId,
  title,
  onOpen,
}: {
  month: string;
  person?: string;
  groupId?: number;
  title: string;
  onOpen: (merchant: string) => void;
}) {
  const q = useQuery({
    queryKey: ["spending", "merchants", month, person, groupId],
    queryFn: () => fetchMerchants(month, { person, group_id: groupId }),
  });
  const total = (q.data ?? []).reduce((s, m) => s + num(m.amount), 0);
  return (
    <section className="card mt-6" aria-label={title}>
      <h2 className="font-display text-xl font-bold">{title}</h2>
      {q.error && (
        <p className="mt-2 text-danger-ink">Could not load the merchants: {(q.error as Error).message}</p>
      )}
      {!q.data && !q.error && <p className="mt-2 text-muted">Loading…</p>}
      {q.data && !q.data.length && (
        <p className="mt-2 text-muted">
          No merchants: months from the Cash Flow sheet have categories, not lines.
        </p>
      )}
      {q.data && q.data.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted">
              <tr>
                <th scope="col" className="px-2 py-1 text-left font-semibold">
                  Merchant
                </th>
                {groupId === undefined && (
                  <th scope="col" className="px-2 py-1 text-left font-semibold">
                    Group
                  </th>
                )}
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Visits
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Spent
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Avg ticket
                </th>
                <th scope="col" className="px-2 py-1 text-left font-semibold">
                  Invoices
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.data.map((m) => (
                <tr key={m.merchant}>
                  <td className="px-2 py-1.5">
                    <button
                      type="button"
                      className="text-left text-primary underline"
                      onClick={() => onOpen(m.merchant)}
                    >
                      {m.merchant}
                    </button>
                  </td>
                  {groupId === undefined && <td className="px-2 py-1.5 text-muted">{m.group_name}</td>}
                  <td className="num px-2 py-1.5 text-right">{m.visits}</td>
                  <td className="num px-2 py-1.5 text-right">{money(m.amount)}</td>
                  <td className="num px-2 py-1.5 text-right">{money(m.avg_ticket)}</td>
                  <td className="px-2 py-1.5">
                    {m.invoices ? (
                      <span className="pill pill-good">
                        {m.invoices} {m.invoices === 1 ? "invoice" : "invoices"}
                      </span>
                    ) : (
                      <span className="text-muted">none</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-line font-semibold">
                <td className="px-2 py-1.5" colSpan={groupId === undefined ? 3 : 2}>
                  Total
                </td>
                <td className="num px-2 py-1.5 text-right">{money(total)}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}

/** Products from the SRI invoices: how often, how much, the price against three months before
 * and a store that sold it for less. */
export function ProductTable({
  month,
  group,
  onGroup,
}: {
  month: string;
  group: string | null;
  onGroup: (g: string | null) => void;
}) {
  const q = useQuery({
    queryKey: ["spending", "products", month],
    queryFn: () => fetchProducts(month),
  });
  const all = q.data ?? [];
  const groups = [...new Set(all.map((p) => p.product_group ?? "Not grouped yet"))].sort();
  const rows = group ? all.filter((p) => (p.product_group ?? "Not grouped yet") === group) : all;
  return (
    <section className="card mt-6" aria-labelledby="products">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="products" className="font-display text-xl font-bold">
          {monthLong(month)} by product, from the invoices
        </h2>
        {groups.length > 1 && (
          <label>
            <span className="label">Product group</span>
            <select
              className="field w-56"
              value={group ?? ""}
              onChange={(e) => onGroup(e.target.value || null)}
            >
              <option value="">Every group</option>
              {groups.map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {q.error && (
        <p className="mt-2 text-danger-ink">Could not load the products: {(q.error as Error).message}</p>
      )}
      {!q.data && !q.error && <p className="mt-2 text-muted">Loading…</p>}
      {q.data && !all.length && (
        <p className="mt-2 text-muted">
          No invoices this month.{" "}
          <Link to="/purchases" className="text-primary underline">
            Upload invoice XMLs on Purchases
          </Link>{" "}
          to see products here.
        </p>
      )}
      {rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted">
              <tr>
                <th scope="col" className="px-2 py-1 text-left font-semibold">
                  Product
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Bought
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Spent
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  Unit price
                </th>
                <th scope="col" className="px-2 py-1 text-right font-semibold">
                  vs 3 months before
                </th>
                <th scope="col" className="px-2 py-1 text-left font-semibold">
                  Cheaper at
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((p) => {
                const ch = p.change === null ? null : num(p.change);
                return (
                  <tr key={p.product_key}>
                    <td className="px-2 py-1.5">
                      {p.description}
                      <span className="block text-xs text-muted">
                        {p.product_group ?? "Not grouped yet"} · {p.stores.join(", ")}
                      </span>
                    </td>
                    <td className="num px-2 py-1.5 text-right">{p.times}×</td>
                    <td className="num px-2 py-1.5 text-right">{money(p.amount)}</td>
                    <td className="num px-2 py-1.5 text-right">{money(p.unit_price)}</td>
                    <td
                      className={`num px-2 py-1.5 text-right ${ch === null ? "text-muted" : ch > 0 ? "text-danger-ink" : ch < 0 ? "text-good-ink" : ""}`}
                    >
                      {ch === null ? "—" : `${ch > 0 ? "+" : ch < 0 ? "−" : ""}${pct(Math.abs(ch))}`}
                    </td>
                    <td className="px-2 py-1.5">
                      {p.cheaper_store ? (
                        <>
                          {p.cheaper_store} <span className="num">{money(p.cheaper_price)}</span>
                          <span className="block text-xs text-good-ink">
                            would have saved <span className="num">{money(p.could_save)}</span>
                          </span>
                        </>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function Ideas({ month, person }: { month: string; person?: string }) {
  const q = useQuery({
    queryKey: ["spending", "ideas", month, person],
    queryFn: () => fetchIdeas(month, person),
  });
  if (!q.data || !q.data.length) return null;
  return (
    <section className="card mt-6" aria-labelledby="ideas">
      <h2 id="ideas" className="font-display text-xl font-bold">
        Ways to save, from {monthLong(month)}’s lines
      </h2>
      <p className="mt-1 text-sm text-muted">
        The amount is what each pattern cost this month, not a promise of savings.
      </p>
      <ul className="mt-3 divide-y divide-line">
        {q.data.map((i) => (
          <li key={i.key} className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-4 py-3">
            <span className="num font-display text-lg font-semibold text-good-ink">{money(i.amount)}</span>
            <div>
              <strong>{i.title}.</strong> <span className="text-muted">{i.detail}</span>
              {i.link && (
                <Link to={i.link} className="ml-1 text-sm font-semibold text-primary">
                  Look →
                </Link>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
