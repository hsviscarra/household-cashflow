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
import DataTable, { type Column } from "../components/DataTable";
import { PersonNote } from "../components/Personalize";
import { localToday, money, monthLong, num } from "../money";
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
const INVOICE_DEFAULTS = ["date", "subtotal", "whose", "category", "sri"];

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
