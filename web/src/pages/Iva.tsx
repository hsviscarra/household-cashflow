import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  fetchIva,
  ivaExcelUrl,
  setIvaIssuer,
  setIvaOpening,
  type InvoiceUpload,
  type IvaMonth,
  type IvaUse,
} from "../api";
import { addMonths, localToday, money, monthLong, num } from "../money";
import { SriImport } from "./Purchases";

// Monthly IVA (ADR-062): the return the accountant prepares, from the SRI's documents. Defaults
// to last month, the one being declared.

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

const USES: [IvaUse, string][] = [
  ["business", "Business (IVA credit)"],
  ["personal", "Personal expense"],
  ["none", "Neither"],
];

export default function IvaPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("month");
  const month =
    raw && /^\d{4}-\d{2}$/.test(raw) ? raw : addMonths(`${localToday().slice(0, 7)}-01`, -1).slice(0, 7);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["iva", month], queryFn: () => fetchIva(month) });
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const r = q.data;

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">Monthly IVA</h1>
          <p className="mt-1 max-w-3xl text-muted">
            The IVA return your accountant prepares, from your SRI documents: what you invoiced, what you
            bought with IVA credit, your personal expenses and the retenciones clients made. Check it,
            download the workbook, and type the Form 104 figures into SRI en línea.
          </p>
        </div>
        <label>
          <span className="label">Month declared</span>
          <input
            type="month"
            className="field w-48"
            value={month}
            onChange={(e) => e.target.value && setParams({ month: e.target.value })}
          />
        </label>
      </header>

      <section className="card space-y-3 p-5" aria-labelledby="bring">
        <h2 id="bring" className="font-display text-xl font-bold">
          Bring in the month's documents
        </h2>
        <p className="text-sm text-muted">
          In SRI en línea → Facturación electrónica, download the month's list of{" "}
          <strong className="text-ink">Comprobantes electrónicos recibidos</strong> (purchases and
          retenciones) and of <strong className="text-ink">emitidos</strong> (your invoices), and upload each
          here. The app gets every document from the SRI by its access key; it already has what came by email.
        </p>
        <SriImport
          onStatus={setStatus}
          onResults={(res: InvoiceUpload[]) => {
            const n = res.filter((x) => x.outcome === "stored").length;
            setStatus({ message: `${n} new documents added.`, tone: "good" });
            qc.invalidateQueries({ queryKey: ["iva"] });
          }}
        />
        {status && (
          <p
            className={`rounded-[10px] p-3 text-sm ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`}
          >
            {status.message}
          </p>
        )}
      </section>

      {q.error && <p className="text-danger-ink">{(q.error as Error).message}</p>}
      {!r && !q.error && <p className="text-muted">Loading…</p>}
      {r && <Body r={r} month={month} />}
    </section>
  );
}

function Body({ r, month }: { r: IvaMonth; month: string }) {
  const f = (k: string) => num(r.form[k] as string);
  const pay = f("f620");
  return (
    <>
      {r.notes.length > 0 && <Opening person={r.person} month={month} />}
      <section aria-labelledby="form104" className="card space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 id="form104" className="font-display text-xl font-bold">
              Form 104 · {monthLong(`${month}-01`)}
            </h2>
            <p className="text-sm text-muted">{r.person}'s return</p>
          </div>
          <div className="text-right">
            <p className="label">To pay (902)</p>
            <p
              className={`num font-display text-3xl font-bold ${pay > 0 ? "text-danger-ink" : "text-good-ink"}`}
            >
              {money(pay)}
            </p>
            <a className="btn btn-secondary mt-2 h-9 px-4 text-sm" href={ivaExcelUrl(month)}>
              Download the workbook
            </a>
          </div>
        </div>
        {r.unclassified > 0 && (
          <p className="rounded-[10px] bg-attention-bg p-3 text-sm text-attention-ink">
            {r.unclassified} invoices below don't say yet whether they're business or personal; until then
            they don't count. Each choice is kept for that issuer.
          </p>
        )}
        <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
          {[
            ["401", "Sales taxed at 15%", f("f401")],
            ["411", "Net of credit notes", f("f411")],
            ["421", "IVA on sales", f("f421")],
            ["500", "Purchases with IVA credit", f("f500")],
            ["510", "Net of credit notes", f("f510")],
            ["520", "IVA on those purchases (credit)", f("f520")],
            ["601", "IVA caused (421 − 520)", f("f601")],
            ["606", "Retenciones credit from last month", f("f606")],
            ["609", "IVA withheld by clients this month", f("f609")],
            ["605", "Purchase credit from last month", f("f605")],
            ["617", "Retenciones credit to next month", f("f617")],
            ["615", "Purchase credit to next month", f("f615")],
          ].map(([code, text, v]) => (
            <div key={code as string} className="flex justify-between gap-3 border-b border-line py-1.5">
              <dt>
                <span className="num mr-2 font-semibold text-muted">{code}</span>
                {text}
              </dt>
              <dd className="num font-semibold">{money(v as number)}</dd>
            </div>
          ))}
        </dl>
        {num(r.income_tax_withheld) > 0 && (
          <p className="text-sm text-muted">
            Income tax withheld this month:{" "}
            <span className="num font-semibold text-ink">{money(r.income_tax_withheld)}</span> (it counts in
            the yearly income tax return, not here).
          </p>
        )}
      </section>

      <Sales r={r} />
      {r.tax_notes.length > 0 && <Notes r={r} />}
      <Purchases r={r} />
    </>
  );
}

function Opening({ person, month }: { person: string; month: string }) {
  const qc = useQueryClient();
  const [purchase, setPurchase] = useState("");
  const [retention, setRetention] = useState("");
  const save = useMutation({
    mutationFn: () =>
      setIvaOpening({
        person,
        month,
        purchase_credit: purchase.replace(/,/g, "") || "0",
        retention_credit: retention.replace(/,/g, "") || "0",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["iva"] }),
  });
  return (
    <section className="card space-y-3 border-attention-line bg-attention-bg p-5 text-attention-ink">
      <h2 className="font-display text-xl font-bold">Credit carried in, once</h2>
      <p className="text-sm">
        From your last return filed before this month, copy field <strong>615</strong> (purchase credit) and
        field <strong>617</strong> (retenciones credit). After this, each month carries its credit to the next
        by itself.
      </p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <label>
          <span className="label">615 · purchases</span>
          <input
            className="field num !w-40"
            inputMode="decimal"
            value={purchase}
            onChange={(e) => setPurchase(e.target.value)}
            placeholder="0.00"
          />
        </label>
        <label>
          <span className="label">617 · retenciones</span>
          <input
            className="field num !w-40"
            inputMode="decimal"
            value={retention}
            onChange={(e) => setRetention(e.target.value)}
            placeholder="0.00"
          />
        </label>
        <button className="btn btn-primary h-10 px-4" disabled={save.isPending}>
          Save
        </button>
        {save.error && <span>{(save.error as Error).message}</span>}
      </form>
    </section>
  );
}

function Sales({ r }: { r: IvaMonth }) {
  return (
    <section aria-labelledby="sales" className="card p-5">
      <h2 id="sales" className="font-display text-xl font-bold">
        Your invoices · {r.sales.length}
      </h2>
      {r.sales.length === 0 ? (
        <p className="mt-2 text-sm text-muted">
          No invoices issued this month. Upload the SRI list of emitidos above.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-muted">
              <tr>
                {[
                  "Date",
                  "Client",
                  "Number",
                  "Base",
                  "IVA",
                  "Total",
                  "Withheld: income",
                  "Withheld: IVA",
                ].map((h, i) => (
                  <th
                    key={h}
                    scope="col"
                    className={`px-2 py-1 font-semibold ${i > 2 ? "text-right" : "text-left"}`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {r.sales.map((s) => (
                <tr key={s.number + s.issue_date}>
                  <td className="px-2 py-2">{day(s.issue_date)}</td>
                  <td className="max-w-64 truncate px-2 py-2">{s.buyer_name}</td>
                  <td className="num px-2 py-2">{s.number}</td>
                  <td className="num px-2 py-2 text-right">{money(num(s.base_taxed) + num(s.base_zero))}</td>
                  <td className="num px-2 py-2 text-right">{money(s.tax)}</td>
                  <td className="num px-2 py-2 text-right font-semibold">{money(s.total)}</td>
                  <td className="num px-2 py-2 text-right">
                    {num(s.income_tax_withheld) ? money(s.income_tax_withheld) : "—"}
                  </td>
                  <td className="num px-2 py-2 text-right">
                    {num(s.iva_withheld) ? money(s.iva_withheld) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Purchases({ r }: { r: IvaMonth }) {
  const qc = useQueryClient();
  const set = useMutation({
    mutationFn: ({ ruc, use }: { ruc: string; use: IvaUse }) => setIvaIssuer(ruc, use),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["iva"] }),
  });
  const order = (u: IvaUse | null) => (u === null ? 0 : u === "business" ? 1 : u === "personal" ? 2 : 3);
  const rows = [...r.purchases].sort((a, b) => order(a.iva_use) - order(b.iva_use));
  return (
    <section aria-labelledby="buys" className="card p-5">
      <h2 id="buys" className="font-display text-xl font-bold">
        Invoices you received · {r.purchases.length}
      </h2>
      <p className="text-sm text-muted">
        Business purchases (internet, phone, your accountant…) give IVA credit; personal expenses go to the
        yearly deduction. The choice is kept for each issuer.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-muted">
            <tr>
              <th scope="col" className="px-2 py-1 text-left font-semibold">
                Date
              </th>
              <th scope="col" className="px-2 py-1 text-left font-semibold">
                Issuer
              </th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">
                Base
              </th>
              <th scope="col" className="px-2 py-1 text-right font-semibold">
                Total
              </th>
              <th scope="col" className="px-2 py-1 text-left font-semibold">
                Counts as
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((p) => (
              <tr key={p.invoice_id} className={p.iva_use === null ? "bg-attention-bg" : ""}>
                <td className="px-2 py-2">{day(p.issue_date)}</td>
                <td className="max-w-72 truncate px-2 py-2" title={p.issuer_name}>
                  {p.issuer_name}
                </td>
                <td className="num px-2 py-2 text-right">{money(num(p.base_taxed) + num(p.base_zero))}</td>
                <td className="num px-2 py-2 text-right">{money(p.total)}</td>
                <td className="px-2 py-2">
                  <select
                    className="field !h-9 !w-52"
                    aria-label={`How ${p.issuer_name} counts`}
                    value={p.iva_use ?? ""}
                    onChange={(e) =>
                      e.target.value && set.mutate({ ruc: p.issuer_ruc, use: e.target.value as IvaUse })
                    }
                  >
                    <option value="">Choose…</option>
                    {USES.map(([v, name]) => (
                      <option key={v} value={v}>
                        {name}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Notes({ r }: { r: IvaMonth }) {
  return (
    <section aria-labelledby="notes" className="card p-5">
      <h2 id="notes" className="font-display text-xl font-bold">
        Credit and debit notes · {r.tax_notes.length}
      </h2>
      <p className="text-sm text-muted">
        A credit note lowers the month's sales (one you issued) or purchases (one you received); a debit note
        raises them. Received notes count only when their issuer is a business purchase.
      </p>
      <ul className="mt-3 divide-y divide-line text-sm">
        {r.tax_notes.map((n) => (
          <li
            key={n.number + n.issue_date}
            className={`flex justify-between gap-4 py-2 ${n.counts ? "" : "text-muted"}`}
          >
            <span className="min-w-0 truncate">
              {day(n.issue_date)} · {n.kind === "credit" ? "Credit" : "Debit"} note{" "}
              {n.direction === "issued" ? "to" : "from"} {n.name}
              {n.modified_number && <span className="text-muted"> · on invoice {n.modified_number}</span>}
              {!n.counts && " · doesn't count"}
            </span>
            <span className="num shrink-0">
              {n.kind === "credit" ? "−" : "+"}
              {money(num(n.base_taxed) + num(n.base_zero))}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
