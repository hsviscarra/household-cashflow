import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  fetchPurchases,
  fetchSriInvoices,
  findSriKeys,
  setProductCategory,
  fetchCategories,
  splitTransaction,
  suggestProductGroups,
  uploadInvoices,
  type Invoice,
  type InvoiceUpload,
  type Purchases,
} from "../api";
import { localToday, money, monthLong, num } from "../money";
import CategoryPicker from "../components/CategoryPicker";

const NOT_GROUPED = "Not grouped yet";
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const qty = (v: string) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 3 });

/** "12 invoices, 9 matched to their payment" */
export function coverageLine(p: Purchases): string {
  const n = p.invoices.length;
  if (!n) return "No invoices for this month yet.";
  const matched = p.invoices.filter((i) => i.paid_with).length;
  return `${n} ${n === 1 ? "invoice" : "invoices"}, ${matched} matched to the card or bank line that paid ${n === 1 ? "it" : "them"}.`;
}

const UPLOAD_WORDS: Record<InvoiceUpload["outcome"], string> = {
  stored: "Added",
  duplicate: "Already here",
  skipped: "Not an invoice",
  rejected: "Refused",
};

export default function PurchasesPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month = raw && /^\d{4}-\d{2}$/.test(raw) ? raw : localToday().slice(0, 7);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["purchases", month], queryFn: () => fetchPurchases(month) });
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const [results, setResults] = useState<InvoiceUpload[]>([]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["purchases"] });

  const upload = useMutation({
    mutationFn: uploadInvoices,
    onSuccess: (r) => {
      setResults(r);
      setStatus(null);
      refresh();
    },
    onError: (e: Error) => setStatus({ message: e.message, tone: "bad" }),
  });
  const suggest = useMutation({
    mutationFn: () => suggestProductGroups(month),
    onSuccess: (r) => {
      setStatus({
        message: r.products
          ? `Claude suggested a group for ${r.products} ${r.products === 1 ? "product" : "products"}. Confirm each one below.`
          : "Every product here already has a group or a suggestion.",
        tone: "good",
      });
      refresh();
    },
    onError: (e: Error) => setStatus({ message: e.message, tone: "bad" }),
  });

  const p = q.data;
  const unsuggested = p?.to_group.filter((u) => !u.suggested_group).length ?? 0;

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {p && p.invoices.length
          ? `What you bought in ${monthLong(`${month}-01`)}: ${money(p.total)}`
          : `Purchases in ${monthLong(`${month}-01`)}`}
      </h1>
      <p className="mt-2 max-w-3xl text-lg text-muted">
        Product by product, from the electronic invoices that reached your Gmail or were uploaded here. For
        the ones that didn’t, download the month’s list in SRI en línea (Facturación electrónica →
        Comprobantes electrónicos recibidos) and upload it: the app gets each invoice from the SRI.{" "}
        <Link to={`/spending?month=${month}&view=products`} className="text-primary underline">
          Compare unit prices and stores
        </Link>
        .
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-4">
        <label>
          <span className="label">Month</span>
          <input
            type="month"
            className="field w-48"
            value={month}
            onChange={(e) => e.target.value && setParams({ month: e.target.value })}
          />
        </label>
        <label className="btn btn-secondary cursor-pointer">
          {upload.isPending ? "Reading invoices…" : "Upload invoice XMLs"}
          <input
            type="file"
            multiple
            accept=".xml,text/xml,application/xml"
            className="sr-only"
            aria-label="Invoice XML files"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (files.length) upload.mutate(files);
            }}
          />
        </label>
        <SriImport
          onStatus={setStatus}
          onResults={(r) => {
            setResults(r);
            refresh();
          }}
        />
        {p?.suggestions_available && unsuggested > 0 && (
          <button className="btn btn-primary" disabled={suggest.isPending} onClick={() => suggest.mutate()}>
            {suggest.isPending ? "Asking Claude…" : `Ask Claude about ${unsuggested} products`}
          </button>
        )}
      </div>

      <p
        aria-live="polite"
        className={
          status
            ? `mt-4 rounded-2xl px-4 py-3 ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`
            : "sr-only"
        }
      >
        {status?.message ?? ""}
      </p>
      {results.length > 0 && (
        <ul aria-label="Upload results" className="mt-4 space-y-1 rounded-2xl bg-surface px-4 py-3 text-sm">
          {results.map((r, i) => (
            <li key={`${r.file_name}-${i}`}>
              <span className="font-semibold">{UPLOAD_WORDS[r.outcome]}:</span> {r.file_name}{" "}
              <span className="text-muted">{r.message}</span>
            </li>
          ))}
        </ul>
      )}

      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load the purchases: {(q.error as Error).message}
        </p>
      )}
      {!p && !q.error && <p className="mt-6 text-muted">Loading the month’s invoices…</p>}
      {p && (
        <>
          <p className="mt-6 text-muted">{coverageLine(p)}</p>
          {p.groups.length > 0 && <GroupBars p={p} />}
          {p.to_group.length > 0 && <ToGroup p={p} onSaved={refresh} />}
          {p.invoices.length > 0 && <InvoiceList invoices={p.invoices} />}
        </>
      )}
    </section>
  );
}

const SRI_BATCH = 10;

/** A text file's contents (FileReader works in every browser and in the tests). */
function readText(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(new Error("The file couldn't be read."));
    r.readAsText(f);
  });
}

/** "Found 12 invoices: 5 new, 7 already here; 2 other documents skipped." */
export function sriFoundLine(k: { new: string[]; stored: number; other: number }): string {
  const n = k.new.length + k.stored;
  if (!n)
    return k.other ? `No invoices in it, only ${k.other} other documents.` : "No access keys found in it.";
  const other = k.other ? `; ${k.other} other ${k.other === 1 ? "document" : "documents"} skipped` : "";
  return `Found ${n} ${n === 1 ? "invoice" : "invoices"}: ${k.new.length} new, ${k.stored} already here${other}.`;
}

/** Invoices that never reached Gmail (ADR-037): the SRI's list of received documents, uploaded or
 * pasted; each new access key is fetched from the SRI in batches of ten. */
export function SriImport({
  onStatus,
  onResults,
}: {
  onStatus: (s: { message: string; tone: "good" | "bad" } | null) => void;
  onResults: (r: InvoiceUpload[]) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState("");
  const run = async (report: string) => {
    onStatus(null);
    try {
      setBusy("Reading the list…");
      const keys = await findSriKeys(report);
      const all: InvoiceUpload[] = [];
      for (let i = 0; i < keys.new.length; i += SRI_BATCH) {
        setBusy(`Getting ${Math.min(i + SRI_BATCH, keys.new.length)} of ${keys.new.length} from the SRI…`);
        all.push(...(await fetchSriInvoices(keys.new.slice(i, i + SRI_BATCH))));
      }
      const stored = all.filter((r) => r.outcome === "stored").length;
      onStatus({
        message: `${sriFoundLine(keys)}${keys.new.length ? ` Added ${stored}.` : ""}`,
        tone: stored === keys.new.length ? "good" : "bad",
      });
      onResults(all.filter((r) => r.outcome !== "stored" || all.length <= 20));
      setText("");
      setPasting(false);
    } catch (e) {
      onStatus({ message: (e as Error).message, tone: "bad" });
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <label className="btn btn-secondary cursor-pointer">
        {busy ?? "Upload the SRI list (.txt)"}
        <input
          type="file"
          accept=".txt,text/plain,.csv"
          className="sr-only"
          aria-label="SRI list of received documents"
          disabled={!!busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void readText(f).then(run);
          }}
        />
      </label>
      <button
        type="button"
        className="btn btn-quiet"
        onClick={() => setPasting(!pasting)}
        aria-expanded={pasting}
      >
        Paste access keys
      </button>
      {pasting && (
        <form
          className="w-full"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) void run(text);
          }}
        >
          <label className="block">
            <span className="label">
              Access keys (49 digits each), or the whole list copied from SRI en línea
            </span>
            <textarea
              className="field h-28 py-2 font-mono text-sm"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary mt-2" disabled={!!busy || !text.trim()}>
            Get these invoices from the SRI
          </button>
        </form>
      )}
    </>
  );
}

/** The month by product group: one bar per group, longest first, with the amount beside it. */
function GroupBars({ p }: { p: Purchases }) {
  const max = Math.max(...p.groups.map((g) => num(g.amount)), 1);
  const total = num(p.total) || 1;
  return (
    <section aria-label="By product group" className="mt-6">
      <h2 className="font-display text-2xl font-bold">By product group</h2>
      <table className="mt-3 w-full max-w-3xl text-sm">
        <caption className="sr-only">Spending by product group</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Group</th>
            <th scope="col">Share</th>
            <th scope="col">Amount</th>
          </tr>
        </thead>
        <tbody>
          {p.groups.map((g) => (
            <tr key={g.group}>
              <th scope="row" className="w-48 py-1.5 pr-3 text-left font-normal">
                {g.group === NOT_GROUPED ? <span className="text-muted">{g.group}</span> : g.group}
              </th>
              <td className="py-1.5">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className={`h-3 rounded-full ${g.group === NOT_GROUPED ? "bg-line" : "bg-primary"}`}
                    style={{ width: `${Math.max(2, (num(g.amount) / max) * 100)}%` }}
                  />
                  <span className="num text-muted">{Math.round((num(g.amount) / total) * 100)}%</span>
                </div>
              </td>
              <td className="num w-28 py-1.5 text-right font-semibold">{money(g.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** Products without a category yet (ADR-050): the app's own categories, chosen once per product. */
function ToGroup({ p, onSaved }: { p: Purchases; onSaved: () => void }) {
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [done, setDone] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: ({ key, id }: { key: string; id: number }) => setProductCategory(key, id),
    onSuccess: (r) => {
      setDone(`${r.product_key}: saved. It gets that category on every invoice, now and later.`);
      onSaved();
    },
  });
  return (
    <section aria-label="Products to categorize" className="mt-10">
      <h2 className="font-display text-2xl font-bold">
        {p.to_group.length} {p.to_group.length === 1 ? "product needs" : "products need"} a category
      </h2>
      <p className="mt-1 text-muted">
        The same categories as the rest of the app. Choose once: the product keeps it on every invoice, and
        you can add a category from the list (for example School fees).
      </p>
      <p
        aria-live="polite"
        className={done ? "mt-3 rounded-2xl bg-good-bg px-4 py-2 text-good-ink" : "sr-only"}
      >
        {done ?? ""}
      </p>
      {save.error && (
        <p className="mt-3 rounded-2xl bg-danger-bg px-4 py-2 text-danger-ink">
          {(save.error as Error).message}
        </p>
      )}
      <ul className="mt-3 divide-y divide-line rounded-2xl border border-line">
        {p.to_group.map((u) => (
          <li key={u.product_key} className="flex flex-wrap items-center gap-3 px-4 py-2">
            <span className="min-w-48 flex-1">
              {u.description}
              <span className="num block text-sm text-muted">
                {money(u.amount)}
                {u.lines > 1 ? ` on ${u.lines} invoices` : ""}
                {u.suggested_group ? ` · looks like ${u.suggested_group}` : ""}
              </span>
            </span>
            <div className="w-64">
              <CategoryPicker
                label={`Category for ${u.description}`}
                hideLabel
                groups={cats.data ?? []}
                value=""
                placeholder="Choose a category"
                onChange={(id) => id !== "" && save.mutate({ key: u.product_key, id })}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** What the paying bank line would split into, by the items' categories (ADR-050). */
export function splitParts(inv: Invoice): { category_id: number; amount: number }[] | null {
  if (!inv.paid_with) return null;
  const by = new Map<number, number>();
  for (const ln of inv.lines) {
    if (!ln.category_id) return null; // every item needs a category first
    by.set(ln.category_id, (by.get(ln.category_id) ?? 0) + num(ln.total));
  }
  if (by.size < 2) return null;
  const parts = [...by.entries()].map(([category_id, amount]) => ({ category_id, amount: Math.round(amount * 100) / 100 }));
  // The invoice total wins over rounding: put the cents on the biggest part.
  const diff = Math.round((num(inv.total) - parts.reduce((s, x) => s + x.amount, 0)) * 100) / 100;
  parts.sort((a, b) => b.amount - a.amount);
  parts[0].amount = Math.round((parts[0].amount + diff) * 100) / 100;
  return parts;
}

function SplitByCategory({ inv }: { inv: Invoice }) {
  const qc = useQueryClient();
  const parts = splitParts(inv);
  const split = useMutation({
    mutationFn: () =>
      splitTransaction(
        inv.paid_with!.transaction_id,
        parts!.map((x) => ({ category_id: x.category_id, amount: (-x.amount).toFixed(2), notes: inv.issuer_name })),
      ),
    onSuccess: () => ["cashflow", "spending", "transactions", "purchases"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
  if (!parts) return null;
  return (
    <div className="mt-3 rounded-2xl bg-surface p-3 text-sm">
      <p>
        This invoice has items in {parts.length} categories. Split the bank line so the cash flow shows each one.
      </p>
      {split.error && <p className="mt-1 text-danger-ink">{(split.error as Error).message}</p>}
      {split.isSuccess ? (
        <p className="mt-1 text-good-ink">Split. The cash flow now counts each category.</p>
      ) : (
        <button className="btn btn-secondary mt-2 h-9 px-3 text-sm" disabled={split.isPending} onClick={() => split.mutate()}>
          Split the bank line by category
        </button>
      )}
    </div>
  );
}

function InvoiceList({ invoices }: { invoices: Invoice[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <section aria-label="Invoices" className="mt-10">
      <h2 className="font-display text-2xl font-bold">Invoices</h2>
      <ul className="mt-3 divide-y divide-line rounded-2xl border border-line">
        {invoices.map((inv) => (
          <li key={inv.invoice_id}>
            <button
              className="flex w-full flex-wrap items-baseline gap-x-3 px-4 py-3 text-left hover:bg-surface"
              aria-expanded={open === inv.invoice_id}
              onClick={() => setOpen(open === inv.invoice_id ? null : inv.invoice_id)}
            >
              <span className="w-16 text-muted">{day(inv.issue_date)}</span>
              <span className="flex-1 font-semibold">{inv.issuer_name}</span>
              <span className="text-sm text-muted">
                {inv.paid_with
                  ? `Paid with ${inv.paid_with.account ?? "a bank line"} on ${day(inv.paid_with.txn_date)}`
                  : "Payment not found yet"}
              </span>
              <span className="num w-24 text-right font-semibold">{money(inv.total)}</span>
            </button>
            {open === inv.invoice_id && (
              <div className="overflow-x-auto px-4 pb-4">
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
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
