// Tax deductions (gastos personales, ADR-036/045): each person's deductible expenses for the tax
// year from the SRI invoices, against the cap their dependents allow, the 18% rebate, and the
// invoices to sort out. Invoices take the app's own categories; the SRI group follows from them.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  chooseGastos,
  fetchGastos,
  fetchGastosInvoices,
  fetchCategories,
  gastosCsvUrl,
  setGastosProfile,
  type GastosChoice,
  type GastosInvoice,
  type GastosPerson,
  type GastosSummary,
  type GpCategory,
} from "../api";
import CategoryPicker from "../components/CategoryPicker";
import { PersonNote } from "../components/Personalize";
import { localToday, money, num } from "../money";
import { usePerson } from "../prefs";

const day = (iso: string) =>
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

/** "USD 1,035.47 back at most" for a person with a known cap */
export function rebateLine(p: GastosPerson, rate: string): string {
  if (p.cap === null) return "The cap for this year isn't known yet: totals only.";
  const room = num(p.cap) - num(p.deductible);
  return room > 0
    ? `${money(room)} more in invoices would still count, up to ${money(num(p.cap) * num(rate))} back.`
    : "At the cap: more invoices won't raise the rebate.";
}

export default function TaxesPage() {
  const thisYear = Number(localToday().slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const [person] = usePerson();
  const [filter, setFilter] = useState<(typeof FILTER_KEYS)[number]>("to_classify");
  const summary = useQuery({ queryKey: ["gastos", year], queryFn: () => fetchGastos(year) });
  const s = summary.data;
  const shown = s?.people.filter((p) => person === "Both" || p.person === person) ?? [];
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">Tax deductions {year}</h1>
          <p className="mt-2 max-w-3xl text-lg text-muted">
            The personal expenses each of you can deduct from your SRI invoices this year, against your cap,
            and the 18% income tax rebate they give back.
          </p>
        </div>
        <label>
          <span className="label">Tax year</span>
          <select className="field" value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {[thisYear, thisYear - 1].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </div>
      <PersonNote person={person} />
      {summary.error && <p className="mt-4 text-danger-ink">{(summary.error as Error).message}</p>}
      {s && (
        <>
          {s.unassigned > 0 && (
            <p className="mt-4 rounded-[14px] border border-attention-line bg-attention-bg px-4 py-3 text-attention-ink">
              <strong>
                {s.unassigned} {s.unassigned === 1 ? "invoice isn't" : "invoices aren't"} anyone's yet
              </strong>{" "}
              ({money(s.unassigned_amount)} before VAT): choose whose they are below, or set INVOICE_BUYERS so
              new ones are recognized.{" "}
              <button type="button" className="font-semibold underline" onClick={() => setFilter("nobody")}>
                Show them
              </button>
            </p>
          )}
          {s.canasta === null && (
            <p className="mt-4 rounded-[14px] bg-surface px-4 py-3 text-sm">
              The SRI's basic basket for {year} isn't in the app yet, so there's no cap: the totals still add
              up.
            </p>
          )}
          <div className={`mt-6 grid gap-6 ${shown.length > 1 ? "xl:grid-cols-2" : ""}`}>
            {shown.map((p) => (
              <PersonCard key={p.person} p={p} s={s} onFilter={() => setFilter("to_classify")} />
            ))}
          </div>
          <Invoices year={year} filter={filter} setFilter={setFilter} person={person} />
          <p className="mt-8 max-w-3xl text-sm text-muted">
            Amounts are the invoices' value before VAT. The cap is 7 basic family baskets with no dependents,
            more with each dependent, 100 for a catastrophic, rare or orphan illness
            {s.canasta ? ` (basket ${money(s.canasta)})` : ""}. This is a projection to fill in the SRI form
            and annex; check the deadlines in the SRI calendar and the final numbers with your accountant.
          </p>
        </>
      )}
    </section>
  );
}

function PersonCard({ p, s, onFilter }: { p: GastosPerson; s: GastosSummary; onFilter: () => void }) {
  const qc = useQueryClient();
  const [cargas, setCargas] = useState(String(p.cargas));
  const save = useMutation({
    mutationFn: (v: { cargas: number; catastrophic: boolean }) =>
      setGastosProfile(s.year, p.person, v.cargas, v.catastrophic),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gastos", s.year] }),
  });
  const share = p.cap ? Math.min(100, (num(p.deductible) / num(p.cap)) * 100) : 0;
  return (
    <section className="card" aria-label={`${p.person}'s tax deductions`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">{p.person}</h2>
        <a className="text-sm font-semibold text-primary underline" href={gastosCsvUrl(s.year, p.person)}>
          Numbers for the annex (CSV)
        </a>
      </div>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="kpi-label">Rebate so far</p>
          <p className="kpi-value num text-primary">{money(p.rebate)}</p>
        </div>
        <div>
          <p className="kpi-label">Counts toward the cap</p>
          <p className="kpi-value num">
            {money(p.deductible)}
            {p.cap && <span className="text-base font-medium text-muted"> of {money(p.cap)}</span>}
          </p>
        </div>
      </div>
      {p.cap && (
        <div
          className="mt-3 h-3 overflow-hidden rounded-full bg-surface"
          role="img"
          aria-label={`${Math.round(share)}% of the cap`}
        >
          <span className="block h-full rounded-full bg-primary" style={{ width: `${share}%` }} />
        </div>
      )}
      <p className="mt-2 text-sm text-muted">{rebateLine(p, s.rate)}</p>
      <table className="mt-4 w-full text-sm">
        <caption className="sr-only">{p.person}'s expenses by SRI category</caption>
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 font-semibold">Category</th>
            <th className="py-1 text-right font-semibold">Invoices</th>
            <th className="py-1 text-right font-semibold">Before VAT</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {p.by_category.map((c) => (
            <tr key={c.category}>
              <td className="py-1.5">{c.label}</td>
              <td className="num py-1.5 text-right">{c.invoices}</td>
              <td className="num py-1.5 text-right">{money(c.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(p.to_classify > 0 || p.not_deductible > 0) && (
        <p className="mt-3 text-sm">
          {p.to_classify > 0 && (
            <button type="button" className="font-semibold text-primary underline" onClick={onFilter}>
              {p.to_classify} {p.to_classify === 1 ? "invoice needs" : "invoices need"} a category
            </button>
          )}
          {p.to_classify > 0 && p.not_deductible > 0 && " · "}
          {p.not_deductible > 0 && <span className="text-muted">{p.not_deductible} not deductible</span>}
        </p>
      )}
      <form
        className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({
            cargas: Math.max(0, Math.min(20, Number(cargas) || 0)),
            catastrophic: p.catastrophic,
          });
        }}
      >
        <label>
          <span className="label">Dependents</span>
          <input
            className="field num w-24"
            type="number"
            min={0}
            max={20}
            value={cargas}
            onChange={(e) => setCargas(e.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={save.isPending}>
          Save
        </button>
        <label className="flex h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={p.catastrophic}
            onChange={(e) => save.mutate({ cargas: p.cargas, catastrophic: e.target.checked })}
          />
          Catastrophic, rare or orphan illness
        </label>
      </form>
    </section>
  );
}

const FILTER_KEYS = ["to_classify", "nobody", "all"] as const;
const FILTERS: [(typeof FILTER_KEYS)[number], string][] = [
  ["to_classify", "Need a category"],
  ["nobody", "Not anyone's"],
  ["all", "All"],
];

function Invoices({
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
      <ul
        className="mt-3 divide-y divide-line rounded-[14px] border border-line bg-ground"
        aria-label="Invoices"
      >
        {rows.map((r) => (
          <InvoiceRow key={r.invoice_id} r={r} year={year} />
        ))}
      </ul>
    </section>
  );
}

function InvoiceRow({ r, year }: { r: GastosInvoice; year: number }) {
  const qc = useQueryClient();
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const groups = cats.data ?? [];
  const [everyIssuer, setEveryIssuer] = useState(false);
  const save = useMutation({
    mutationFn: (body: GastosChoice) => chooseGastos(r.invoice_id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gastos", year] }),
  });
  const why = guessWords(r);
  return (
    <li className="grid gap-2 px-4 py-3 md:grid-cols-[1fr_auto] md:items-center">
      <div>
        <p className="font-semibold">
          {r.issuer_name} <span className="num text-sm font-normal text-muted">RUC {r.issuer_ruc}</span>
        </p>
        <p className="text-sm text-muted">
          {day(r.issue_date)} · invoice {r.number} · <span className="num">{money(r.subtotal)}</span> before
          VAT, <span className="num">{money(r.total)}</span> paid
          {r.person_source === "paid" && " · whose: from the line that paid it"}
          {why && ` · category: ${why}`}
        </p>
      </div>
      <div className="grid gap-2 md:flex md:flex-wrap md:items-center">
        <label className="sr-only" htmlFor={`who-${r.invoice_id}`}>
          Whose invoice
        </label>
        <select
          id={`who-${r.invoice_id}`}
          className="field h-10 md:!w-36"
          value={r.person ?? ""}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ person: (e.target.value || null) as GastosChoice["person"] })}
        >
          <option value="">Nobody</option>
          <option value="Hernan">Hernan</option>
          <option value="Lauren">Lauren</option>
        </select>
        <div className="md:w-72">
          <CategoryPicker
            label={`Category for ${r.issuer_name}`}
            hideLabel
            groups={groups}
            value={r.category_id ?? ""}
            placeholder="Choose a category"
            onChange={(id) =>
              save.mutate({ category_id: id === "" ? null : id, remember_issuer: everyIssuer })
            }
          />
        </div>
        <span className={`pill ${r.category && r.category !== "none" ? "" : "text-muted"}`}>
          {sriWords(r)}
        </span>
        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={everyIssuer} onChange={(e) => setEveryIssuer(e.target.checked)} />
          All from this supplier
        </label>
      </div>
      {save.error && <p className="text-sm text-danger-ink">{(save.error as Error).message}</p>}
    </li>
  );
}

const LABEL: Record<GpCategory, string> = {
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
