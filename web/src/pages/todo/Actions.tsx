import {
  type TodoTask,
  setHoldingValue,
  updateHolding,
  dismissTodo,
  createRule,
  type Owner,
  markInstallmentPaid,
  createTemplate,
} from "../../api";
import { type Ctx } from "./shared";
import { Categorize, Who, Purpose } from "./Who";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import CategoryPicker from "../../components/CategoryPicker";
import { money } from "../../money";
import { billName } from "../Recurring";

export function Action({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  switch (t.kind) {
    case "categorize":
      return <Categorize t={t} ctx={ctx} />;
    case "who":
      return <Who t={t} ctx={ctx} />;
    case "transfer":
      return <Who t={t} ctx={ctx} transfer />;
    case "duplicate":
    case "stale":
      return <Value t={t} ctx={ctx} />;
    case "rule":
      return <Suggestion t={t} ctx={ctx} />;
    case "bill":
      return <AddBill t={t} ctx={ctx} />;
    case "loan":
      return <LoanPaid t={t} ctx={ctx} />;
    case "invoices":
      return <Go to={t.link}>Sort them out</Go>;
    case "purpose":
      return <Purpose t={t} ctx={ctx} />;
    default:
      return <Go to={t.link || "/"}>{GO[t.kind] ?? "Open"}</Go>;
  }
}

export const GO: Record<string, string> = {
  statement: "Upload it",
  import: "Review the import",
  recurring: "See bills",
  balance: "Check it",
};

export function Go({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="btn btn-secondary h-9 px-4 text-sm" to={to}>
      {children}
    </Link>
  );
}

export function Value({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  const holding = t.data.holding_id as number | null;
  const [amount, setAmount] = useState("");
  const today = new Date().toISOString().slice(0, 10);
  const save = useMutation({
    mutationFn: () => setHoldingValue(holding as number, { as_of: today, amount: amount.replace(/,/g, "") }),
    onSuccess: () => ctx.finish(t.key, `Saved today's value of ${t.title}.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const pause = useMutation({
    mutationFn: () => updateHolding(holding as number, { is_active: false }),
    onSuccess: () => ctx.finish(t.key, `Stopped counting ${t.title}; it no longer counts in net worth.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const later = useDismiss(t, ctx, `Fine, it won't ask about ${t.title} again.`);
  if (holding === null)
    return (
      <>
        <Go to="/import">Upload its statement</Go>
        <button
          className="btn btn-quiet h-9 px-3 text-sm"
          disabled={later.isPending}
          onClick={() => later.mutate()}
        >
          Don't ask again
        </button>
      </>
    );
  return (
    <>
      {t.kind === "duplicate" && (
        <button
          className="btn btn-primary h-9 px-4 text-sm"
          disabled={pause.isPending}
          onClick={() => pause.mutate()}
        >
          Stop counting it
        </button>
      )}
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (amount.trim()) save.mutate();
        }}
      >
        <input
          className="field num !w-36"
          inputMode="decimal"
          aria-label={`Today's value of ${t.title}`}
          placeholder="Today's value"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button
          className={`btn h-9 px-4 text-sm ${t.kind === "duplicate" ? "btn-secondary" : "btn-primary"}`}
          disabled={!amount.trim() || save.isPending}
        >
          Save value
        </button>
      </form>
      {t.kind !== "duplicate" && (
        <button
          className="btn btn-secondary h-9 px-3 text-sm"
          disabled={pause.isPending}
          onClick={() => pause.mutate()}
        >
          Stop counting it
        </button>
      )}
    </>
  );
}

export function useDismiss(t: TodoTask, ctx: Ctx, text: string) {
  return useMutation({
    mutationFn: () => dismissTodo(t.key),
    onSuccess: () => ctx.finish(t.key, text),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
}

export function Suggestion({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  const save = useMutation({
    mutationFn: (category_id: number) =>
      createRule({
        pattern: t.data.pattern as string,
        match_type: "contains",
        category_id,
        priority: 50,
        set_person: (t.data.person as Owner | null) ?? null,
      }),
    onSuccess: (r) => ctx.finish(t.key, `Rule saved: ${r.pattern} → ${r.category_path}.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const no = useDismiss(t, ctx, "Fine, it won't suggest that rule again.");
  return (
    <>
      <button
        className="btn btn-primary h-9 px-4 text-sm"
        disabled={save.isPending}
        onClick={() => save.mutate(t.data.category_id as number)}
      >
        Save rule
      </button>
      <span className="text-sm text-muted">or with</span>
      <div className="w-64 max-w-full">
        <CategoryPicker
          label={`Different category for ${t.data.pattern as string}`}
          hideLabel
          groups={ctx.groups}
          value=""
          placeholder="A different category…"
          onChange={(cid) => cid !== "" && save.mutate(cid)}
        />
      </div>
      <button className="btn btn-quiet h-9 px-3 text-sm" disabled={no.isPending} onClick={() => no.mutate()}>
        No
      </button>
    </>
  );
}

export function LoanPaid({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  const paid = useMutation({
    mutationFn: () => markInstallmentPaid(t.data.holding_id as number, t.data.number as number),
    onSuccess: (r) => ctx.finish(t.key, `Marked paid. The balance is now ${money(r.balance_after)}.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  return (
    <>
      <button
        className="btn btn-primary h-9 px-4 text-sm"
        disabled={paid.isPending}
        onClick={() => paid.mutate()}
      >
        Yes, paid
      </button>
      <Link className="btn btn-quiet h-9 px-4 text-sm" to={t.link}>
        See the loan
      </Link>
    </>
  );
}

export function AddBill({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  const d = t.data;
  const add = useMutation({
    mutationFn: () =>
      createTemplate({
        name: billName(d.merchant as string),
        category_id: d.category_id as number,
        type: "expense",
        amount: d.amount as string,
        start_month: `${(d.last_date as string).slice(0, 7)}-01`,
        account_id: (d.account_id as number | null) ?? null,
        person: (d.person as Owner | null) ?? null,
        match_pattern: (d.match_pattern as string | null) ?? null,
        every_months: d.every_months as number,
        due_day: d.due_day as number,
      }),
    onSuccess: (r) => ctx.finish(t.key, `Added ${r.name} to your bills.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const no = useDismiss(t, ctx, "Fine, it won't suggest that bill again.");
  return (
    <>
      <button
        className="btn btn-primary h-9 px-4 text-sm"
        disabled={add.isPending}
        onClick={() => add.mutate()}
      >
        Add to bills
      </button>
      <button className="btn btn-quiet h-9 px-3 text-sm" disabled={no.isPending} onClick={() => no.mutate()}>
        Not a bill
      </button>
    </>
  );
}
