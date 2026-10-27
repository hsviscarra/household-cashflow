import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { fetchSubscriptions, type Subscription } from "../api";
import { money } from "../money";

const CADENCE: Record<Subscription["cadence"], { title: string; help: string }> = {
  weekly: { title: "Weekly", help: "Charged every week; app stores bill some apps this way." },
  monthly: { title: "Monthly", help: "" },
  quarterly: { title: "Every three months", help: "" },
  yearly: { title: "Yearly", help: "" },
  possible: {
    title: "Possible subscriptions",
    help: "In a Subscriptions & Software category but not repeating yet: seen once, or at uneven intervals.",
  },
};
const ORDER: Subscription["cadence"][] = ["weekly", "monthly", "quarterly", "yearly", "possible"];

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export default function SubscriptionsPage() {
  const q = useQuery({ queryKey: ["subscriptions"], queryFn: fetchSubscriptions });
  const data = q.data;
  const active = data?.subscriptions.filter((s) => s.active && s.cadence !== "possible") ?? [];
  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">
        {data && active.length
          ? `${active.length} subscriptions cost ${money(data.monthly_cost)} a month`
          : "Subscriptions"}
      </h1>
      <p className="mt-2 text-lg text-muted">
        Charges that repeat at a steady interval with a similar amount, found in your card and bank
        statements.
      </p>
      {q.error && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load subscriptions: {(q.error as Error).message}
        </p>
      )}
      {!data && !q.error && <p className="mt-6 text-muted">Looking for repeating charges…</p>}
      {data && (
        <>
          {data.subscriptions.length === 0 ? (
            <p className="mt-6 rounded-2xl bg-info-bg px-5 py-4">
              No repeating charges found yet. They appear once statements cover a few weeks or months.{" "}
              <Link className="text-primary underline" to="/import">
                Upload statements
              </Link>
            </p>
          ) : (
            <dl className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-3">
              <Tile label="Each month" value={money(data.monthly_cost)} />
              <Tile label="Each year" value={money(Number(data.monthly_cost) * 12)} />
              <Tile label="Weekly app billing, a month" value={money(data.weekly_monthly_cost)} />
            </dl>
          )}
          {ORDER.map((cadence) => {
            const list = data.subscriptions.filter((s) => s.cadence === cadence);
            if (!list.length) return null;
            return (
              <section key={cadence} className="mt-8" aria-labelledby={`cadence-${cadence}`}>
                <h2 id={`cadence-${cadence}`} className="font-display text-2xl font-bold">
                  {CADENCE[cadence].title}
                </h2>
                {CADENCE[cadence].help && <p className="mt-1 text-muted">{CADENCE[cadence].help}</p>}
                <ul
                  className="mt-3 divide-y divide-line rounded-2xl border border-line"
                  aria-label={CADENCE[cadence].title}
                >
                  {list.map((s) => (
                    <SubscriptionRow key={s.merchant} s={s} />
                  ))}
                </ul>
              </section>
            );
          })}
        </>
      )}
    </section>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="num mt-1 font-display text-2xl font-bold">{value}</dd>
    </div>
  );
}

function SubscriptionRow({ s }: { s: Subscription }) {
  const [open, setOpen] = useState(false);
  const possible = s.cadence === "possible";
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 md:flex-nowrap">
        <button className="min-w-0 flex-1 text-left" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span className="font-mono text-sm font-semibold">{s.merchant}</span>
          <span className="block text-sm text-muted">
            {s.accounts.join(", ") || "—"}
            {s.category_path ? ` · ${s.category_path}` : ""} · {s.charges.length}{" "}
            {s.charges.length === 1 ? "charge" : "charges"}, last {day(s.last)}
            {s.next_expected && s.active ? ` · next about ${day(s.next_expected)}` : ""}
          </span>
        </button>
        <span className="flex shrink-0 items-center gap-3">
          {!possible && (
            <span className={`pill ${s.active ? "pill-good" : "bg-attention-bg text-attention-ink"}`}>
              {s.active ? "Active" : "Stopped?"}
            </span>
          )}
          <span className="text-right">
            <span className="num block">{money(s.typical)}</span>
            {!possible && (
              <span className="num block text-sm text-muted">
                {money(s.monthly_cost)} a month · {money(s.yearly_cost)} a year
              </span>
            )}
          </span>
        </span>
      </div>
      {open && (
        <ul className="mt-2 divide-y divide-line text-sm" aria-label={`Charges of ${s.merchant}`}>
          {s.charges.map((c) => (
            <li key={c.transaction_id} className="flex justify-between gap-3 py-1">
              <span>
                <span className="num">{day(c.txn_date)}</span>
                <span className="text-muted"> · {c.account_name ?? "—"}</span>
                <span className="block font-mono text-xs">{c.description}</span>
              </span>
              <span className="num">{money(c.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
