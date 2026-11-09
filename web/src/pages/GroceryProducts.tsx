import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  fetchGroceryProducts,
  labelGroceries,
  setGroceryLabels,
  type GroceryProduct,
  type GroceryProducts,
} from "../api";
import { addMonths, money, monthLong, num } from "../money";

// Groceries → Products (ADR-061): every supermarket product of a period, totals by aisle, type
// or brand, and the labels to correct. Claude labels new products on its own when the page opens.

export const AISLES = [
  "Meat & Fish",
  "Dairy & Eggs",
  "Fruit & Vegetables",
  "Bakery",
  "Pantry",
  "Snacks & Sweets",
  "Drinks",
  "Alcohol",
  "Frozen & Ready Meals",
  "Baby",
  "Household & Cleaning",
  "Personal Care",
  "Health & Pharmacy",
  "Pets",
  "Services",
  "Car",
  "Other",
];
const PERIODS: [number, string][] = [
  [1, "This month"],
  [3, "3 months"],
  [12, "12 months"],
];
const BY = { by_group: "Aisle", by_type: "Type", by_brand: "Brand" } as const;
type By = keyof typeof BY;
const FIELD: Record<By, keyof GroceryProduct> = {
  by_group: "product_group",
  by_type: "product_type",
  by_brand: "brand",
};
const UNKNOWN = "Unknown";

export default function GroceryProducts({ month }: { month: string }) {
  const [months, setMonths] = useState(1);
  const [by, setBy] = useState<By>("by_type");
  const [pick, setPick] = useState<string | null>(null);
  const [text, setText] = useState("");
  const start = addMonths(`${month}-01`, -(months - 1));
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["groceries", "products", start, months],
    queryFn: () => fetchGroceryProducts(start, months),
  });
  const [tried, setTried] = useState<string | null>(null);
  const label = useMutation({
    mutationFn: () => labelGroceries(start, months),
    onSettled: () => qc.invalidateQueries({ queryKey: ["groceries"] }),
  });
  const key = `${start}/${months}`;
  useEffect(() => {
    if (q.data && q.data.unlabeled > 0 && tried !== key && !label.isPending) {
      setTried(key);
      label.mutate();
    }
  }, [q.data, tried, key, label]);

  const p = q.data;
  const rows = useMemo(() => {
    if (!p) return [];
    const words = text.trim().toLowerCase();
    return p.products.filter(
      (r) =>
        (pick === null || ((r[FIELD[by]] as string | null) ?? UNKNOWN) === pick) &&
        (!words || `${r.description} ${r.product_type ?? ""} ${r.brand ?? ""}`.toLowerCase().includes(words)),
    );
  }, [p, pick, by, text]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div role="radiogroup" aria-label="Period" className="flex rounded-[10px] bg-surface p-1 text-sm">
          {PERIODS.map(([n, name]) => (
            <button
              key={n}
              role="radio"
              aria-checked={months === n}
              onClick={() => {
                setMonths(n);
                setPick(null);
              }}
              className={`rounded-lg px-3 py-1.5 font-semibold ${months === n ? "bg-ground shadow-sm" : "text-muted"}`}
            >
              {name}
            </button>
          ))}
        </div>
        <p className="text-sm text-muted">
          {months === 1 ? monthLong(`${month}-01`) : `${monthLong(start)} to ${monthLong(`${month}-01`)}`}
          {p && (
            <>
              {" · "}
              <span className="num font-semibold text-ink">{money(p.total)}</span> on {p.products.length}{" "}
              products
            </>
          )}
        </p>
      </div>
      {label.isPending && (
        <p role="status" className="rounded-[10px] bg-info-bg p-3 text-sm text-info-ink">
          Claude is labeling {p?.unlabeled ?? ""} new products (aisle, type and brand)…
        </p>
      )}
      {label.error && (label.error as { status?: number }).status !== 503 && (
        <p className="rounded-[10px] bg-danger-bg p-3 text-sm text-danger-ink">
          {(label.error as Error).message}
        </p>
      )}
      {q.error && <p className="text-danger-ink">{(q.error as Error).message}</p>}
      {!p && !q.error && <p className="text-muted">Loading…</p>}
      {p && p.products.length === 0 && (
        <p className="card p-6 text-muted">No supermarket invoices in this period.</p>
      )}
      {p && p.products.length > 0 && (
        <>
          <Totals p={p} by={by} setBy={setBy} pick={pick} setPick={setPick} />
          <section aria-labelledby="all-products" className="card p-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 id="all-products" className="font-display text-xl font-bold">
                {pick ? `${BY[by]}: ${pick}` : "Every product"}{" "}
                <span className="num text-muted">· {rows.length}</span>
              </h2>
              <div className="flex items-center gap-2">
                {pick && (
                  <button className="btn btn-quiet h-9 px-3 text-sm" onClick={() => setPick(null)}>
                    Show all
                  </button>
                )}
                <input
                  className="field !w-56"
                  aria-label="Search products"
                  placeholder="Search a product or brand"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </div>
            </div>
            <ProductTable rows={rows} />
          </section>
        </>
      )}
    </div>
  );
}

function Totals({
  p,
  by,
  setBy,
  pick,
  setPick,
}: {
  p: GroceryProducts;
  by: By;
  setBy: (b: By) => void;
  pick: string | null;
  setPick: (s: string | null) => void;
}) {
  const list = p[by].slice(0, 15);
  const top = Math.max(1, ...list.map((t) => num(t.amount)));
  return (
    <section aria-labelledby="totals" className="card space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="totals" className="font-display text-xl font-bold">
          Where it goes
        </h2>
        <div role="radiogroup" aria-label="Total by" className="flex rounded-[10px] bg-surface p-1 text-sm">
          {(Object.keys(BY) as By[]).map((k) => (
            <button
              key={k}
              role="radio"
              aria-checked={by === k}
              onClick={() => {
                setBy(k);
                setPick(null);
              }}
              className={`rounded-lg px-3 py-1.5 font-semibold ${by === k ? "bg-ground shadow-sm" : "text-muted"}`}
            >
              By {BY[k].toLowerCase()}
            </button>
          ))}
        </div>
      </div>
      <ul className="grid gap-x-8 gap-y-3 md:grid-cols-2">
        {list.map((t) => {
          const on = pick === t.name;
          return (
            <li key={t.name}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => setPick(on ? null : t.name)}
                className={`w-full rounded-lg p-1 text-left ${on ? "bg-nav-active" : "hover:bg-surface"}`}
              >
                <span className="flex justify-between gap-3 text-sm">
                  <span className="truncate font-medium">{t.name}</span>
                  <span className="num shrink-0">
                    {money(t.amount)} <span className="text-muted">· {t.products}</span>
                  </span>
                </span>
                <span className="mt-1 block h-2 rounded-full bg-surface">
                  <span
                    className="block h-2 rounded-full bg-flow-in"
                    style={{ width: `${(num(t.amount) / top) * 100}%` }}
                  />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {p[by].length > list.length && (
        <p className="text-sm text-muted">
          And {p[by].length - list.length} more; search below to find them.
        </p>
      )}
    </section>
  );
}

function ProductTable({ rows }: { rows: GroceryProduct[] }) {
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-muted">
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Product
            </th>
            <th scope="col" className="px-2 py-1 text-left font-semibold">
              Aisle · type · brand
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              Bought
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              Unit price
            </th>
            <th scope="col" className="px-2 py-1 text-right font-semibold">
              Spent
            </th>
            <th scope="col">
              <span className="sr-only">Edit</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) =>
            editing === r.product_key ? (
              <EditRow key={r.product_key} r={r} done={() => setEditing(null)} />
            ) : (
              <tr key={r.product_key}>
                <td className="max-w-72 truncate px-2 py-2" title={r.description}>
                  {r.description}
                </td>
                <td className="px-2 py-2">
                  <span className="text-muted">{r.product_group ?? "—"} · </span>
                  <span className="font-medium">{r.product_type ?? "—"}</span>
                  <span className="text-muted"> · {r.brand ?? "no brand"}</span>
                  {r.label_source === "claude" && <span className="pill ml-2 text-xs">Claude</span>}
                </td>
                <td className="num px-2 py-2 text-right">
                  {Number(r.quantity).toLocaleString("en-US", { maximumFractionDigits: 3 })} · {r.times}×
                </td>
                <td className="num px-2 py-2 text-right">{money(r.unit_price)}</td>
                <td className="num px-2 py-2 text-right font-semibold">{money(r.amount)}</td>
                <td className="px-2 py-2 text-right">
                  <button
                    className="text-primary underline"
                    aria-label={`Edit ${r.description}`}
                    onClick={() => setEditing(r.product_key)}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </div>
  );
}

function EditRow({ r, done }: { r: GroceryProduct; done: () => void }) {
  const qc = useQueryClient();
  const [group, setGroup] = useState(r.product_group ?? "");
  const [type, setType] = useState(r.product_type ?? "");
  const [brand, setBrand] = useState(r.brand ?? "");
  const save = useMutation({
    mutationFn: () =>
      setGroceryLabels({
        product_key: r.product_key,
        product_group: group || null,
        product_type: type.trim() || null,
        brand: brand.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["groceries"] });
      done();
    },
  });
  return (
    <tr className="bg-surface">
      <td className="px-2 py-2 font-medium">{r.description}</td>
      <td colSpan={4} className="px-2 py-2">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <select
            className="field !w-48"
            aria-label="Aisle"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
          >
            <option value="">No aisle</option>
            {AISLES.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
          <input
            className="field !w-40"
            aria-label="Type"
            placeholder="Type, e.g. Cheese"
            value={type}
            onChange={(e) => setType(e.target.value)}
          />
          <input
            className="field !w-40"
            aria-label="Brand"
            placeholder="Brand, e.g. Kiosko"
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
          />
          <button className="btn btn-primary h-9 px-4 text-sm" disabled={save.isPending}>
            Save for every purchase
          </button>
          <button type="button" className="btn btn-quiet h-9 px-3 text-sm" onClick={done}>
            Cancel
          </button>
          {save.error && <span className="text-danger-ink">{(save.error as Error).message}</span>}
        </form>
      </td>
      <td />
    </tr>
  );
}
