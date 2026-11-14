import {
  type SheetItem,
  type LoanSchedule,
  uploadLoanTable,
  fetchLoanPayments,
  setHoldingValue,
  deleteHoldingValue,
} from "../../api";
import { money, monthLong, num } from "../../money";
import { useState } from "react";
import { whatIf, type Notify, useRefresh, day, today, SOURCE } from "./shared";
import { useQueryClient, useMutation, useQuery } from "@tanstack/react-query";

/** "10 of 12 installments paid · next 1,022.50 in November 2026 · paid off December 2026" */
export function ScheduleLine({
  schedule: s,
}: {
  schedule: NonNullable<NonNullable<SheetItem["loan"]>["schedule"]>;
}) {
  return (
    <div className="mt-2 text-sm">
      <p>
        {s.paid} of {s.installments} installments paid
        {s.next_period && s.next_total && (
          <>
            {" "}
            · next <span className="num">{money(s.next_total)}</span> in {monthLong(s.next_period)}
          </>
        )}
        {s.payoff && s.left > 0 && <> · paid off {monthLong(s.payoff)}</>}
        {s.left === 0 && <> · paid off</>}
      </p>
      <p className="text-muted">
        Interest this year <span className="num">{money(s.interest_this_year)}</span> · still to pay{" "}
        <span className="num">{money(s.interest_left)}</span> interest and{" "}
        <span className="num">{money(s.other_left)}</span> insurance and charges over {s.left}{" "}
        {s.left === 1 ? "month" : "months"}
      </p>
    </div>
  );
}

/** "Paying 100 more a month ends it 3 years sooner and saves 4,200 of interest." */
export function WhatIf({ schedule, name }: { schedule: LoanSchedule; name: string }) {
  const [extra, setExtra] = useState("100");
  const r = whatIf(schedule, num(extra));
  return (
    <div className="mt-2 rounded-xl bg-surface px-3 py-2 text-sm">
      <label className="flex flex-wrap items-center gap-2">
        Paying
        <input
          className="field num h-9"
          style={{ width: "6.5rem" }}
          inputMode="decimal"
          aria-label={`Extra a month on ${name}`}
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
        />
        more a month
      </label>
      {r && r.sooner <= 0 ? (
        <p className="mt-1 text-muted">still ends with the last payment ({schedule.left} left).</p>
      ) : r ? (
        <p className="mt-1">
          ends it{" "}
          <strong>
            {r.sooner >= 12
              ? `${Math.floor(r.sooner / 12)} ${Math.floor(r.sooner / 12) === 1 ? "year" : "years"}${r.sooner % 12 ? ` ${r.sooner % 12} months` : ""}`
              : `${r.sooner} ${r.sooner === 1 ? "month" : "months"}`}{" "}
            sooner
          </strong>{" "}
          ({r.months} payments instead of {schedule.left}) and saves about{" "}
          <strong className="num">{money(r.saved)}</strong> of interest.
        </p>
      ) : (
        <p className="mt-1 text-muted">Enter an amount to see how much sooner it ends.</p>
      )}
    </div>
  );
}

export function LoanTableUpload({
  item,
  notify,
  replacing,
}: {
  item: SheetItem;
  notify: Notify;
  replacing: boolean;
}) {
  const refresh = useRefresh();
  const qc = useQueryClient();
  const send = useMutation({
    mutationFn: (file: File) => uploadLoanTable(item.holding_id!, file),
    onSuccess: (r) => {
      notify(
        `Read ${r.installments} installments: ${r.paid} paid, ${r.due} to go` +
          (r.balance != null ? `; balance ${money(r.balance)}.` : "."),
      );
      qc.invalidateQueries({ queryKey: ["loan-payments", item.holding_id] });
      refresh();
    },
    onError: (e: Error) => notify(`Could not read the table: ${e.message}`, "bad"),
  });
  return (
    <label className="btn btn-quiet h-9 cursor-pointer px-3 text-sm">
      {send.isPending
        ? "Reading…"
        : replacing
          ? "Upload a newer amortization table"
          : "Upload amortization table (PDF)"}
      <input
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        aria-label={`Amortization table for ${item.name}`}
        disabled={send.isPending}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) send.mutate(file);
        }}
      />
    </label>
  );
}

export function Payments({ item }: { item: SheetItem }) {
  const q = useQuery({
    queryKey: ["loan-payments", item.holding_id],
    queryFn: () => fetchLoanPayments(item.holding_id!),
  });
  if (q.error)
    return <p className="mt-3 text-sm text-danger-ink">Could not load the payments: {q.error.message}</p>;
  if (!q.data) return <p className="mt-3 text-sm text-muted">Loading the payments…</p>;
  const paid = q.data.filter((p) => p.status === "paid");
  const found = paid.filter((p) => p.line_id != null).length;
  return (
    <div className="mt-3">
      <p className="text-sm text-muted">
        {found} of {paid.length} paid installments found in the bank lines (same amount within 1.00, around
        its month).
      </p>
      <ul className="mt-2 divide-y divide-line text-sm" aria-label={`Payments for ${item.name}`}>
        {q.data.map((p) => (
          <li key={p.number} className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5">
            <span>
              <span className="num">#{p.number}</span> · {monthLong(p.period)} ·{" "}
              <span className="num">{money(p.total)}</span>
            </span>
            <span
              className={p.line_id != null ? "" : p.status === "paid" ? "text-attention-ink" : "text-muted"}
            >
              {p.line_id != null
                ? `Paid ${day(p.line_date!)} from ${p.account_name ?? "an account"} (${money(Math.abs(num(p.line_amount)))})`
                : p.status === "paid"
                  ? "Lender says paid; no bank line found"
                  : "Due"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ValueForm({ item, notify, onDone }: { item: SheetItem; notify: Notify; onDone: () => void }) {
  const refresh = useRefresh();
  const [asOf, setAsOf] = useState(today());
  const [amount, setAmount] = useState("");
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () => setHoldingValue(item.holding_id!, { as_of: asOf, amount, notes: notes || null }),
    onSuccess: () => {
      refresh();
      notify(`${item.name}: ${money(amount)} on ${day(asOf)}.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-3 grid gap-2 rounded-2xl bg-surface p-3 md:grid-cols-3"
      aria-label={`New value for ${item.name}`}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label>
        <span className="label">{item.purchase ? "Paid so far" : "Value"}</span>
        <input
          className="field num"
          type="number"
          required
          min={0}
          step="0.01"
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </label>
      <label>
        <span className="label">On</span>
        <input
          className="field"
          type="date"
          required
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Note (optional)</span>
        <input className="field" maxLength={400} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="md:col-span-3">
        <button className="btn btn-secondary" disabled={save.isPending || !amount}>
          Save value
        </button>
      </div>
    </form>
  );
}

export function History({ item, notify }: { item: SheetItem; notify: Notify }) {
  const refresh = useRefresh();
  const remove = useMutation({
    mutationFn: deleteHoldingValue,
    onSuccess: () => {
      refresh();
      notify("Value removed.");
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <ul className="mt-3 divide-y divide-line text-sm" aria-label={`History of ${item.name}`}>
      {[...item.history].reverse().map((v, i) => (
        <li key={`${v.as_of}-${i}`} className="flex items-center justify-between gap-2 py-1">
          <span>
            {day(v.as_of)} <span className="text-muted">· {SOURCE[v.source] ?? v.source}</span>
            {v.notes && <span className="block text-xs text-muted">{v.notes}</span>}
          </span>
          <span className="flex items-center gap-2">
            <span className="num">{money(v.amount)}</span>
            {v.source === "manual" && v.snapshot_id != null && (
              <button
                className="btn btn-quiet h-8 px-2 text-xs"
                aria-label={`Remove the value of ${day(v.as_of)}`}
                onClick={() => remove.mutate(v.snapshot_id!)}
              >
                Remove
              </button>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
