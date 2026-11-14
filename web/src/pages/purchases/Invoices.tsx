import { type Invoice, splitTransaction } from "../../api";
import { num, money } from "../../money";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import DataTable, { type Column } from "../../components/DataTable";
import { useState } from "react";

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const qty = (v: string) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 3 });

/** What the paying bank line would split into, by the items' categories (ADR-050). */
export function splitParts(inv: Invoice): { category_id: number; amount: number }[] | null {
  if (!inv.paid_with) return null;
  const by = new Map<number, number>();
  for (const ln of inv.lines) {
    if (!ln.category_id) return null; // every item needs a category first
    by.set(ln.category_id, (by.get(ln.category_id) ?? 0) + num(ln.total));
  }
  if (by.size < 2) return null;
  const parts = [...by.entries()].map(([category_id, amount]) => ({
    category_id,
    amount: Math.round(amount * 100) / 100,
  }));
  // The invoice total wins over rounding: put the cents on the biggest part.
  const diff = Math.round((num(inv.total) - parts.reduce((s, x) => s + x.amount, 0)) * 100) / 100;
  parts.sort((a, b) => b.amount - a.amount);
  parts[0].amount = Math.round((parts[0].amount + diff) * 100) / 100;
  return parts;
}

export function SplitByCategory({ inv }: { inv: Invoice }) {
  const qc = useQueryClient();
  const parts = splitParts(inv);
  const split = useMutation({
    mutationFn: () =>
      splitTransaction(
        inv.paid_with!.transaction_id,
        parts!.map((x) => ({
          category_id: x.category_id,
          amount: (-x.amount).toFixed(2),
          notes: inv.issuer_name,
        })),
      ),
    onSuccess: () =>
      ["cashflow", "spending", "transactions", "purchases"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      ),
  });
  if (!parts) return null;
  return (
    <div className="mt-3 rounded-2xl bg-surface p-3 text-sm">
      <p>
        This invoice has items in {parts.length} categories. Split the bank line so the cash flow shows each
        one.
      </p>
      {split.error && <p className="mt-1 text-danger-ink">{(split.error as Error).message}</p>}
      {split.isSuccess ? (
        <p className="mt-1 text-good-ink">Split. The cash flow now counts each category.</p>
      ) : (
        <button
          className="btn btn-secondary mt-2 h-9 px-3 text-sm"
          disabled={split.isPending}
          onClick={() => split.mutate()}
        >
          Split the bank line by category
        </button>
      )}
    </div>
  );
}

export const paidWith = (inv: Invoice) =>
  inv.paid_with
    ? `Paid with ${inv.paid_with.account ?? "a bank line"} on ${day(inv.paid_with.txn_date)}`
    : "Payment not found yet";

export const INVOICE_COLUMNS = (open: number | null, toggle: (id: number) => void): Column<Invoice>[] => [
  {
    id: "supplier",
    label: "Supplier",
    fixed: true,
    sort: (i) => i.issuer_name,
    group: (i) => i.issuer_name,
    cell: (i) => (
      <button
        className="text-left font-semibold text-primary underline"
        aria-expanded={open === i.invoice_id}
        onClick={() => toggle(i.invoice_id)}
      >
        {i.issuer_name}
      </button>
    ),
  },
  {
    id: "date",
    label: "Date",
    sort: (i) => i.issue_date,
    date: (i) => i.issue_date,
    cell: (i) => day(i.issue_date),
  },
  {
    id: "payment",
    label: "Payment",
    sort: (i) => i.paid_with?.txn_date ?? "",
    group: (i) => (i.paid_with ? (i.paid_with.account ?? "A bank line") : "Payment not found yet"),
    cell: (i) => <span className="text-muted">{paidWith(i)}</span>,
  },
  {
    id: "received_by",
    label: "In whose name",
    sort: (i) => i.received_by,
    group: (i) => i.received_by || "Nobody",
    cell: (i) => i.received_by,
  },
  {
    id: "number",
    label: "Number",
    sort: (i) => i.number,
    cell: (i) => <span className="num">{i.number}</span>,
  },
  {
    id: "products",
    label: "Products",
    align: "right",
    sort: (i) => i.lines.length,
    cell: (i) => i.lines.length,
  },
  {
    id: "subtotal",
    label: "Before tax",
    align: "right",
    sort: (i) => num(i.subtotal),
    total: (i) => num(i.subtotal),
    cell: (i) => money(i.subtotal),
  },
  {
    id: "tax",
    label: "VAT",
    align: "right",
    sort: (i) => num(i.tax),
    total: (i) => num(i.tax),
    cell: (i) => money(i.tax),
  },
  {
    id: "total",
    label: "Total",
    align: "right",
    fixed: "end",
    sort: (i) => num(i.total),
    total: (i) => num(i.total),
    cell: (i) => <span className="font-semibold">{money(i.total)}</span>,
  },
];

// The month's invoices on the shared table (ADR-091, ADR-095): sort, group by supplier, payment
// or person with subtotals, and find an invoice by a product on it. The products open under the row.
export function InvoiceList({ invoices }: { invoices: Invoice[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const columns = INVOICE_COLUMNS(open, (id) => setOpen(open === id ? null : id));
  return (
    <section aria-label="Invoices" className="mt-10">
      <h2 className="font-display text-2xl font-bold">Invoices</h2>
      <div className="mt-3">
        <DataTable
          table="purchases-invoices"
          filter
          caption="The month's invoices"
          columns={columns}
          rows={invoices}
          rowKey={(i) => i.invoice_id}
          defaults={["date", "payment"]}
          search={(i) =>
            `${i.issuer_name} ${i.number} ${i.received_by} ${i.lines.map((ln) => ln.description).join(" ")}`
          }
          expanded={(i) => (open === i.invoice_id ? <InvoiceProducts inv={i} /> : null)}
        />
      </div>
    </section>
  );
}

export function InvoiceProducts({ inv }: { inv: Invoice }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">
          Products on invoice {inv.number} from {inv.issuer_name}
        </caption>
        <thead className="text-muted">
          <tr>
            {["Product", "Quantity", "Price", "Total", "Category"].map((h, i) => (
              <th
                key={h}
                scope="col"
                className={`py-1 font-semibold ${i && i < 4 ? "text-right" : "text-left"} ${i === 4 ? "pl-4" : ""}`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {inv.lines.map((ln) => (
            <tr key={ln.line_no}>
              <td className="py-1">{ln.description}</td>
              <td className="num py-1 text-right">{qty(ln.quantity)}</td>
              <td className="num py-1 text-right">{money(ln.unit_price)}</td>
              <td className="num py-1 text-right">{money(ln.total)}</td>
              <td className="py-1 pl-4 text-muted">{ln.category_path ?? ln.product_group ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="num mt-2 text-sm text-muted">
        Invoice {inv.number}: {money(inv.subtotal)} before tax, VAT {money(inv.tax)}
      </p>
      <SplitByCategory inv={inv} />
    </div>
  );
}
