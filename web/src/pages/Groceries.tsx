import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { fetchGroceries, type Groceries } from "../api";
import { addMonths, localToday, money, monthLong, monthShort, num, pct } from "../money";
import { Legend, StackedColumns } from "../components/charts";
import GroceryProducts from "./GroceryProducts";
import GroceryTrends from "./GroceryTrends";

// Groceries (ADR-059): the month's supermarket spending (statements) next to what the invoices
// say it bought. Defaults to last month, the latest one whose statements are usually in.

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export default function GroceriesPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month =
    raw && /^\d{4}-\d{2}$/.test(raw) ? raw : addMonths(`${localToday().slice(0, 7)}-01`, -1).slice(0, 7);
  const v = params.get("view");
  const view = v === "products" || v === "trends" ? v : "overview";
  const q = useQuery({
    queryKey: ["groceries", month],
    queryFn: () => fetchGroceries(`${month}-01`),
    enabled: view === "overview",
  });
  const g = q.data;
  const show = (to: string) => setParams({ month, ...(to !== "overview" ? { view: to } : {}) });

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">Groceries</h1>
          <p className="mt-1 max-w-3xl text-muted">
            What the supermarket money buys: the Groceries spending from your statements, and the products on
            the Supermaxi, Megamaxi and other supermarket invoices that reach your email.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div role="radiogroup" aria-label="View" className="flex rounded-[10px] bg-surface p-1 text-sm">
            {[
              ["overview", "Overview"],
              ["trends", "Trends"],
              ["products", "Products"],
            ].map(([to, name]) => (
              <button
                key={to}
                role="radio"
                aria-checked={view === to}
                onClick={() => show(to)}
                className={`rounded-lg px-3 py-1.5 font-semibold ${view === to ? "bg-ground shadow-sm" : "text-muted"}`}
              >
                {name}
              </button>
            ))}
          </div>
          <label>
            <span className="label">Month</span>
            <input
              type="month"
              className="field w-48"
              value={month}
              onChange={(e) =>
                e.target.value &&
                setParams({ month: e.target.value, ...(view !== "overview" ? { view } : {}) })
              }
            />
          </label>
        </div>
      </header>
      {view === "products" && <GroceryProducts month={month} />}
      {view === "trends" && <GroceryTrends month={month} />}
      {q.error && (
        <p role="alert" className="card border-danger-ink p-4 text-danger-ink">
          {(q.error as Error).message}
        </p>
      )}
      {view === "overview" && !g && !q.error && <p className="text-muted">Loading…</p>}
      {view === "overview" && g && <Body g={g} month={month} />}
    </section>
  );
}

function Body({ g, month }: { g: Groceries; month: string }) {
  const spent = num(g.spent);
  const covered = spent > 0 ? Math.min(num(g.invoiced) / spent, 1) : 0;
  const vsUsual = num(g.usual) > 0 ? spent / num(g.usual) - 1 : null;
  const perWeek = num(g.weeks) > 0 ? spent / num(g.weeks) : 0;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label={`Spent in ${monthLong(`${month}-01`)}`} value={money(g.spent)}>
          {vsUsual === null
            ? "No months before to compare"
            : `${vsUsual >= 0 ? "+" : ""}${pct(vsUsual)} vs usual`}
        </Tile>
        <Tile label="Usual month" value={num(g.usual) > 0 ? money(g.usual) : "—"}>
          {num(g.usual) > 0 ? "Average of the 3 months before" : "Not enough months before yet"}
        </Tile>
        <Tile label="A week" value={money(perWeek)}>
          This month's spending ÷ {num(g.weeks).toFixed(1)} weeks
        </Tile>
        <Tile label="With its invoice" value={pct(covered)}>
          {money(g.invoiced)} of {money(g.spent)} shows its products
        </Tile>
      </div>

      <Trend g={g} month={month} />

      {g.missing.length > 0 && (
        <section aria-labelledby="missing" className="card space-y-3 p-5">
          <div>
            <h2 id="missing" className="font-display text-xl font-bold">
              Charges without their invoice · {g.missing.length}
            </h2>
            <p className="text-sm text-muted">
              Give your cédula at the till so the invoice reaches your email, or download the month's list in
              SRI en línea and upload it on{" "}
              <Link to={`/purchases?month=${month}`} className="text-primary underline">
                Purchases
              </Link>
              . Until then, what these bought isn't known.
            </p>
          </div>
          <ul className="divide-y divide-line text-sm">
            {g.missing.map((c) => (
              <li key={c.transaction_id} className="flex justify-between gap-4 py-2">
                <span className="min-w-0 truncate">
                  {day(c.txn_date)} · {c.merchant}
                  {c.account_name && <span className="text-muted"> · {c.account_name}</span>}
                </span>
                <span className="num shrink-0">{money(c.amount)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Aisles g={g} month={month} />
        <Stores g={g} />
      </div>
      <Products g={g} month={month} />
    </>
  );
}

function Tile({ label, value, children }: { label: string; value: string; children: ReactNode }) {
  return (
    <div className="card p-5">
      <p className="label">{label}</p>
      <p className="num mt-1 font-display text-3xl font-bold">{value}</p>
      <p className="mt-1 text-sm text-muted">{children}</p>
    </div>
  );
}

function Trend({ g, month }: { g: Groceries; month: string }) {
  const [, setParams] = useSearchParams();
  const data = g.trend.map((p) => ({
    key: p.month.slice(0, 7),
    label: monthShort(p.month),
    selected: p.month.slice(0, 7) === month,
    line: num(p.spent) > 0 ? num(p.spent) : undefined,
    segments: [{ key: "invoiced", value: num(p.invoiced), color: "var(--color-cat-groceries)" }],
    tooltip: (
      <>
        <p className="font-semibold">{monthLong(p.month)}</p>
        <p className="num">Spent {money(p.spent)}</p>
        <p className="num text-muted">With invoices {money(p.invoiced)}</p>
      </>
    ),
  }));
  return (
    <section aria-labelledby="trend" className="card space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="trend" className="font-display text-xl font-bold">
          The last six months
        </h2>
        <Link to={`?month=${month}&view=trends`} className="text-sm text-primary underline">
          A year by aisle, comparisons and patterns
        </Link>
      </div>
      <StackedColumns
        data={data}
        title="Grocery spending, last six months"
        onSelect={(m) => setParams({ month: m })}
      />
      <div className="flex flex-wrap items-center gap-4">
        <Legend items={[{ label: "With invoices", color: "var(--color-cat-groceries)" }]} />
        <span className="flex items-center gap-2 text-sm text-muted">
          <span aria-hidden className="inline-block h-0.5 w-5 bg-ink" /> Spent (statements)
        </span>
      </div>
    </section>
  );
}

function Aisles({ g, month }: { g: Groceries; month: string }) {
  const top = Math.max(1, ...g.aisles.map((a) => Math.max(num(a.amount), num(a.usual))));
  return (
    <section aria-labelledby="aisles" className="card space-y-3 p-5">
      <h2 id="aisles" className="font-display text-xl font-bold">
        By aisle
      </h2>
      {g.aisles.length === 0 && <p className="text-sm text-muted">No supermarket invoices this month.</p>}
      <ul className="space-y-3">
        {g.aisles.map((a) => (
          <li key={a.name}>
            <div className="flex justify-between gap-3 text-sm">
              <span className="font-medium">{a.name}</span>
              <span className="num">
                {money(a.amount)}
                {num(a.usual) > 0 && <span className="text-muted"> · usual {money(a.usual)}</span>}
              </span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-surface">
              <div
                className="h-2 rounded-full bg-flow-in"
                style={{ width: `${(num(a.amount) / top) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
      {g.ungrouped_products > 0 && (
        <p className="rounded-[10px] bg-attention-bg p-3 text-sm text-attention-ink">
          {g.ungrouped_products} products aren't in an aisle yet.{" "}
          <Link to={`/purchases?month=${month}`} className="font-semibold underline">
            Sort them on Purchases
          </Link>{" "}
          (Claude can suggest each one); the app remembers them for next time.
        </p>
      )}
    </section>
  );
}

function Stores({ g }: { g: Groceries }) {
  return (
    <section aria-labelledby="stores" className="card space-y-3 p-5">
      <h2 id="stores" className="font-display text-xl font-bold">
        Stores
      </h2>
      {g.stores.length === 0 && <p className="text-sm text-muted">No supermarket invoices this month.</p>}
      <ul className="divide-y divide-line text-sm">
        {g.stores.map((s) => (
          <li key={s.name} className="flex justify-between gap-4 py-2">
            <span className="min-w-0 truncate">
              {s.name}{" "}
              <span className="text-muted">
                · {s.invoices} {s.invoices === 1 ? "invoice" : "invoices"}
              </span>
            </span>
            <span className="num shrink-0">{money(s.amount)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Products({ g, month }: { g: Groceries; month: string }) {
  if (!g.products.length) return null;
  return (
    <section aria-labelledby="products" className="card p-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="products" className="font-display text-xl font-bold">
          Top products
        </h2>
        <Link to={`?month=${month}&view=products`} className="text-sm text-primary underline">
          Every product, by type and brand
        </Link>
      </div>
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
                Unit price
              </th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">
                vs before
              </th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">
                Spent
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {g.products.map((p) => {
              const ch = p.change === null ? null : num(p.change);
              return (
                <tr key={p.product_key}>
                  <td className="max-w-72 truncate px-2 py-2" title={p.description}>
                    {p.description}
                    {p.product_group && <span className="block text-xs text-muted">{p.product_group}</span>}
                  </td>
                  <td className="num px-2 py-2 text-right">
                    {Number(p.quantity).toLocaleString("en-US", { maximumFractionDigits: 3 })} · {p.times}×
                  </td>
                  <td className="num px-2 py-2 text-right">{money(p.unit_price)}</td>
                  <td
                    className={`num px-2 py-2 text-right ${ch === null ? "text-muted" : ch > 0.02 ? "text-danger-ink" : ch < -0.02 ? "text-good-ink" : ""}`}
                  >
                    {ch === null ? "new" : `${ch > 0 ? "+" : ""}${pct(ch)}`}
                  </td>
                  <td className="num px-2 py-2 text-right font-semibold">{money(p.amount)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
