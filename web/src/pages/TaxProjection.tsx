import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { fetchTaxProjection, saveTaxProfile, type PersonTax, type TaxProfile, type TaxRegime } from "../api";
import { localToday, money, num } from "../money";
import { usePerson } from "../prefs";

// Taxes → Income tax (ADR-088): what each person is projected to owe for the year, how much more
// in invoices would still lower it, and what to set aside each month until the payment.

const REGIMES: [TaxRegime, string][] = [
  ["employee", "Employee: the employer withholds"],
  ["foreign", "Paid from abroad: nothing withheld"],
  ["independent", "Independent: invoices"],
];
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });

export default function TaxProjectionPage() {
  const thisYear = Number(localToday().slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const [person] = usePerson();
  const q = useQuery({ queryKey: ["tax-projection", year], queryFn: () => fetchTaxProjection(year) });
  const shown = (q.data ?? []).filter((p) => person === "Both" || p.person === person);
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">Income tax {year}</h1>
          <p className="mt-2 max-w-3xl text-lg text-muted">
            What each of you is projected to owe for the year, how much more in invoices would still lower it,
            and what to set aside each month until it's paid.
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
      {q.error && (
        <p role="alert" className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          {(q.error as Error).message}
        </p>
      )}
      {q.isLoading && <p className="mt-6 text-muted">Loading…</p>}
      <div className={`mt-6 grid gap-6 ${shown.length > 1 ? "xl:grid-cols-2" : ""}`}>
        {shown.map((p) => (
          <PersonCard key={`${p.person}-${p.year}`} p={p} />
        ))}
      </div>
      {q.data && (
        <p className="mt-8 max-w-3xl text-sm text-muted">
          An estimate, not a return. Income is what reached the bank in each person's Salary category, plus a
          typical month for the months to come; the tax is the SRI's table for the year; the rebate is 18% of
          the deductible invoices on{" "}
          <Link className="text-primary underline" to="/taxes">
            Deductions
          </Link>
          . The payment shows in the{" "}
          <Link className="text-primary underline" to="/projections">
            forecast
          </Link>{" "}
          in March. Check the final numbers and your due date with your accountant.
        </p>
      )}
    </section>
  );
}

function PersonCard({ p }: { p: PersonTax }) {
  const owes = num(p.to_pay) > 0;
  return (
    <section className="card" aria-label={`${p.person}'s income tax`}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-2xl font-bold">{p.person}</h2>
        <div className="text-right">
          <p className="kpi-label">{owes ? "To pay with the return" : "In your favour"}</p>
          <p className={`kpi-value num ${owes ? "" : "text-good-ink"}`}>{money(Math.abs(num(p.to_pay)))}</p>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        {owes ? (
          <>
            Due around {day(p.pay_on)}. Setting aside{" "}
            <span className="num font-semibold text-ink">{money(p.set_aside)}</span> a month for{" "}
            {p.months_left} month{p.months_left === 1 ? "" : "s"} covers it.
          </>
        ) : (
          "Nothing to set aside: what was withheld covers the tax."
        )}
      </p>

      <table className="mt-4 w-full text-sm">
        <caption className="sr-only">{p.person}'s income tax, step by step</caption>
        <tbody className="divide-y divide-line">
          <Row label="Income received so far" value={p.received} />
          <Row
            label="Income for the whole year"
            hint={`the months to come at ${money(p.typical_month)} each`}
            value={p.projected_income}
          />
          <Row
            label="Taxable income"
            hint="plus withheld, less exempt income and deductions"
            value={p.taxable}
          />
          <Row label="Tax by the SRI's table" value={p.tax} />
          <Row
            label="Rebate for personal expenses"
            hint={`18% of ${money(p.expenses)} in invoices`}
            value={p.rebate}
            minus
          />
          <Row label="Tax after the rebate" value={p.due} strong />
          {(p.profile.regime === "employee" || num(p.profile.withheld) > 0) && (
            <Row label="Withheld by the employer" value={p.profile.withheld} minus />
          )}
        </tbody>
      </table>

      {num(p.more_rebate) > 0 && (
        <p className="mt-4 rounded-[10px] bg-info-bg p-3 text-sm text-info-ink">
          <span className="num font-semibold">{money(p.room)}</span> more in deductible invoices before
          December 31 would still count, taking up to{" "}
          <span className="num font-semibold">{money(p.more_rebate)}</span> off the tax.{" "}
          <Link className="font-semibold underline" to="/taxes">
            See the invoices
          </Link>
        </p>
      )}
      {p.notes.length > 0 && (
        <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-attention-ink">
          {p.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <ProfileForm p={p} />
    </section>
  );
}

function Row({
  label,
  hint,
  value,
  minus = false,
  strong = false,
}: {
  label: string;
  hint?: string;
  value: string;
  minus?: boolean;
  strong?: boolean;
}): ReactNode {
  return (
    <tr className={strong ? "font-semibold" : undefined}>
      <th scope="row" className="py-1.5 text-left font-normal">
        <span className={strong ? "font-semibold" : undefined}>{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </th>
      <td className="num py-1.5 text-right align-top">
        {minus && num(value) > 0 ? "−" : ""}
        {money(value)}
      </td>
    </tr>
  );
}

function ProfileForm({ p }: { p: PersonTax }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<TaxProfile>(p.profile);
  const save = useMutation({
    mutationFn: () => saveTaxProfile(p.year, p.person, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tax-projection", p.year] });
      qc.invalidateQueries({ queryKey: ["projections"] });
    },
  });
  const amount = (key: "withheld" | "exempt" | "deductions", label: string, hint: string) => (
    <label>
      <span className="label">{label}</span>
      <input
        className="field num !w-36"
        inputMode="decimal"
        aria-describedby={`${p.person}-${key}-hint`}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value.replace(/,/g, "") })}
      />
      <span id={`${p.person}-${key}-hint`} className="mt-1 block max-w-36 text-xs text-muted">
        {hint}
      </span>
    </label>
  );
  return (
    <form
      className="mt-4 flex flex-wrap items-start gap-3 border-t border-line pt-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label>
        <span className="label">How {p.person} is taxed</span>
        <select
          className="field !w-auto"
          value={form.regime}
          onChange={(e) => setForm({ ...form, regime: e.target.value as TaxRegime })}
        >
          {REGIMES.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {amount("withheld", "Withheld in the year", "By the employer, from the payslips")}
      {amount("exempt", "Exempt income", "Décimos that reached the bank")}
      {amount("deductions", "Deductions", "IESS paid on your own, costs")}
      <button type="submit" className="btn btn-secondary mt-6" disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save"}
      </button>
      {save.error && (
        <p role="alert" className="w-full text-sm text-danger-ink">
          {(save.error as Error).message}
        </p>
      )}
    </form>
  );
}
