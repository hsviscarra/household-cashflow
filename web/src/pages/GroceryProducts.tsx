import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  fetchGroceryProducts,
  labelGroceries,
  setGroceryLabels,
  type GroceryProduct,
  type GroceryProducts,
} from "../api";
import DataTable, { type Column } from "../components/DataTable";
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

const COLUMNS = (edit: (key: string) => void): Column<GroceryProduct>[] => [
  {
    id: "product",
    label: "Product",
    fixed: true,
    sort: (r) => r.description,
    cell: (r) => (
      <span className="block max-w-72 truncate" title={r.description}>
        {r.description}
        {r.label_source === "claude" && <span className="pill ml-2 text-xs">Claude</span>}
      </span>
    ),
  },
  {
    id: "aisle",
    label: "Aisle",
    sort: (r) => r.product_group ?? "",
    group: (r) => r.product_group ?? UNKNOWN,
    cell: (r) => r.product_group ?? "—",
  },
  {
    id: "type",
    label: "Type",
    sort: (r) => r.product_type ?? "",
    group: (r) => r.product_type ?? UNKNOWN,
    cell: (r) => <span className="font-medium">{r.product_type ?? "—"}</span>,
  },
  {
    id: "brand",
    label: "Brand",
    sort: (r) => r.brand ?? "",
    group: (r) => r.brand ?? UNKNOWN,
    cell: (r) => r.brand ?? <span className="text-muted">no brand</span>,
  },
  {
    id: "store",
    label: "Store",
    sort: (r) => r.stores.join(", "),
    cell: (r) => r.stores.join(", "),
  },
  {
    id: "quantity",
    label: "Bought",
    align: "right",
    sort: (r) => num(r.quantity),
    cell: (r) => Number(r.quantity).toLocaleString("en-US", { maximumFractionDigits: 3 }),
  },
  { id: "times", label: "Times", align: "right", sort: (r) => r.times, cell: (r) => `${r.times}×` },
  {
    id: "unit_price",
    label: "Unit price",
    align: "right",
    sort: (r) => num(r.unit_price),
    cell: (r) => money(r.unit_price),
  },
  {
    id: "amount",
    label: "Spent",
    align: "right",
    fixed: "end",
    sort: (r) => num(r.amount),
    total: (r) => num(r.amount),
    cell: (r) => <span className="font-semibold">{money(r.amount)}</span>,
  },
  {
    id: "edit",
    label: "Edit",
    header: <span className="sr-only">Edit</span>,
    align: "right",
    fixed: "end",
    cell: (r) => (
      <button
        className="text-primary underline"
        aria-label={`Edit ${r.description}`}
        onClick={() => edit(r.product_key)}
      >
        Edit
      </button>
    ),
  },
];

// On the shared table (ADR-091): columns, order, sort and grouping with subtotals are the
// person's; the label editor opens under the row.
function ProductTable({ rows }: { rows: GroceryProduct[] }) {
  const [editing, setEditing] = useState<string | null>(null);
  const columns = useMemo(() => COLUMNS(setEditing), []);
  return (
    <div className="mt-3">
      <DataTable
        table="grocery-products"
        caption="Every product bought in the period"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.product_key}
        defaults={["aisle", "type", "brand", "quantity", "times", "unit_price"]}
        defaultSort={{ id: "amount", dir: "desc" }}
        expanded={(r) => (editing === r.product_key ? <EditRow r={r} done={() => setEditing(null)} /> : null)}
      />
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
    <form
      aria-label={`Labels of ${r.description}`}
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
  );
}
