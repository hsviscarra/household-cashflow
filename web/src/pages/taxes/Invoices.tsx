import {
  type GastosInvoice,
  fetchGastosInvoices,
  fetchCategories,
  type GastosChoice,
  chooseGastos,
  type GpCategory,
} from "../../api";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import DataTable, { type Column } from "../../components/DataTable";
import { monthLong, num, money } from "../../money";
import CategoryPicker from "../../components/CategoryPicker";

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

/** Why a guess was made, in words. */
export function guessWords(r: GastosInvoice): string | null {
  switch (r.category_source) {
    case "issuer":
      return "same as every invoice from this supplier";
    case "claude":
      return "Claude's reading of this supplier: change it if it's wrong";
    case "paid":
      return `paid as ${r.paid_as ?? "its category"}`;
    case "products":
      return r.category === "salud" ? "mostly pharmacy products" : "mostly food";
    default:
      return null;
  }
}

export const FILTER_KEYS = ["to_classify", "nobody", "all"] as const;

export const FILTERS: [(typeof FILTER_KEYS)[number], string][] = [
  ["to_classify", "Need a category"],
  ["nobody", "Not anyone's"],
  ["all", "All"],
];

export function Invoices({
  year,
  filter,
  setFilter,
  person,
}: {
  year: number;
  filter: (typeof FILTER_KEYS)[number];
  setFilter: (f: (typeof FILTER_KEYS)[number]) => void;
  person: string;
}) {
  const q = useQuery({
    queryKey: ["gastos", year, "invoices", filter],
    queryFn: () => fetchGastosInvoices(year, filter),
  });
  const rows = (q.data ?? []).filter((r) => person === "Both" || filter === "nobody" || r.person === person);
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const groups = cats.data ?? [];
  // On by default: one choice settles every invoice of the supplier that has none of its own.
  const [everyIssuer, setEveryIssuer] = useState(true);
  const save = useMutation({
    mutationFn: ({ id, body }: { id: number; body: GastosChoice }) =>
      chooseGastos(id, { ...body, remember_issuer: everyIssuer }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gastos", year] }),
  });
  const columns: Column<GastosInvoice>[] = [
    {
      id: "supplier",
      label: "Supplier",
      fixed: true,
      sort: (r) => r.issuer_name,
      group: (r) => r.issuer_name,
      cell: (r) => (
        <>
          <span className="font-semibold">{r.issuer_name}</span>
          <span className="num block text-xs text-muted">RUC {r.issuer_ruc}</span>
        </>
      ),
    },
    {
      id: "date",
      label: "Date",
      sort: (r) => r.issue_date,
      date: (r) => r.issue_date,
      group: (r) => monthLong(`${r.issue_date.slice(0, 7)}-01`),
      cell: (r) => <span className="num whitespace-nowrap">{day(r.issue_date)}</span>,
    },
    {
      id: "number",
      label: "Invoice",
      sort: (r) => r.number,
      cell: (r) => <span className="num">{r.number}</span>,
    },
    {
      id: "subtotal",
      label: "Before VAT",
      align: "right",
      sort: (r) => num(r.subtotal),
      total: (r) => num(r.subtotal),
      cell: (r) => money(r.subtotal),
    },
    {
      id: "total",
      label: "Paid",
      align: "right",
      sort: (r) => num(r.total),
      total: (r) => num(r.total),
      cell: (r) => money(r.total),
    },
    {
      id: "whose",
      label: "Whose",
      sort: (r) => r.person ?? "",
      group: (r) => r.person ?? "Nobody",
      cell: (r) => (
        <>
          <select
            aria-label={`Whose invoice from ${r.issuer_name}`}
            className="field h-10 !w-32"
            value={r.person ?? ""}
            disabled={save.isPending}
            onChange={(e) =>
              save.mutate({
                id: r.invoice_id,
                body: { person: (e.target.value || null) as GastosChoice["person"] },
              })
            }
          >
            <option value="">Nobody</option>
            <option value="Hernan">Hernan</option>
            <option value="Lauren">Lauren</option>
          </select>
          {r.person_source === "paid" && (
            <span className="block text-xs text-muted">from the line that paid it</span>
          )}
        </>
      ),
    },
    {
      id: "category",
      label: "Category",
      sort: (r) => r.category_path ?? "",
      group: (r) => r.category_path ?? "No category",
      cell: (r) => (
        <div className="w-64">
          <CategoryPicker
            label={`Category for ${r.issuer_name}`}
            hideLabel
            groups={groups}
            value={r.category_id ?? ""}
            placeholder="Choose a category"
            onChange={(id) => save.mutate({ id: r.invoice_id, body: { category_id: id === "" ? null : id } })}
          />
        </div>
      ),
    },
    {
      id: "sri",
      label: "For the SRI",
      sort: (r) => sriWords(r),
      group: (r) => sriWords(r),
      cell: (r) => (
        <>
          <span
            className={`pill whitespace-nowrap ${r.category && r.category !== "none" ? "" : "text-muted"}`}
          >
            {sriWords(r)}
          </span>
          {guessWords(r) && <span className="mt-1 block text-xs text-muted">{guessWords(r)}</span>}
        </>
      ),
    },
    {
      id: "paid_as",
      label: "Paid with",
      sort: (r) => r.paid_as ?? "",
      cell: (r) => <span className="text-muted">{r.paid_as ?? "Payment not found yet"}</span>,
    },
  ];
  return (
    <section className="mt-10" aria-labelledby="gp-invoices">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="gp-invoices" className="font-display text-2xl font-bold">
          Invoices
        </h2>
        <div
          role="group"
          aria-label="Which invoices"
          className="inline-flex rounded-[10px] bg-surface p-1 text-sm"
        >
          {FILTERS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={filter === k}
              className={`h-9 rounded-lg px-3 font-semibold ${filter === k ? "bg-ground text-ink shadow-sm" : "text-muted"}`}
              onClick={() => setFilter(k)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {q.isLoading && <p className="mt-3 text-muted">Loading…</p>}
      {q.data && rows.length === 0 && (
        <p className="mt-3 text-muted">
          {filter === "to_classify"
            ? "Every invoice has a category."
            : filter === "nobody"
              ? "Every invoice is someone's."
              : "No invoices this year yet."}
        </p>
      )}
      {rows.length > 0 && (
        <>
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={everyIssuer} onChange={(e) => setEveryIssuer(e.target.checked)} />
            A choice applies to all from the same supplier that have none of their own
          </label>
          {save.error && (
            <p role="alert" className="mt-2 text-sm text-danger-ink">
              {(save.error as Error).message}
            </p>
          )}
          <div className="mt-2">
            <DataTable
              table="gastos-invoices"
              filter
              caption={`Invoices of ${year}`}
              columns={columns}
              rows={rows}
              rowKey={(r) => r.invoice_id}
              defaults={INVOICE_DEFAULTS}
              defaultSort={{ id: "date", dir: "desc" }}
              search={(r) =>
                `${r.issuer_name} ${r.issuer_ruc} ${r.number} ${r.category_path ?? ""} ${r.person ?? ""} ${r.subtotal} ${r.total}`
              }
            />
          </div>
        </>
      )}
    </section>
  );
}

// The columns shown until a person chooses their own (ADR-091).
export const INVOICE_DEFAULTS = ["date", "subtotal", "whose", "category", "sri"];

export const LABEL: Record<GpCategory, string> = {
  alimentacion: "Food",
  salud: "Health",
  educacion: "Education, arts & culture",
  vivienda: "Housing",
  vestimenta: "Clothing",
  turismo: "Domestic tourism",
};

/** What the invoice counts as for the SRI, from its category. */
export function sriWords(r: Pick<GastosInvoice, "category">): string {
  if (r.category === "none") return "Not deductible";
  if (!r.category) return "No SRI group yet";
  return `Deducts as ${LABEL[r.category]}`;
}
