import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import {
  createPerson,
  createRule,
  createTemplate,
  dismissTodo,
  fetchCategories,
  fetchPeople,
  fetchTodo,
  markInstallmentPaid,
  oneSidedTransfer,
  resolveMerchant,
  setHoldingValue,
  setWho,
  statementPageUrl,
  updateHolding,
  updateTransaction,
  type CategoryGroup,
  type Owner,
  type TodoSection,
  type TodoTask,
} from "../api";
import CategoryPicker from "../components/CategoryPicker";
import { money } from "../money";
import { billName } from "./Recurring";

// To do (ADR-047, ADR-058): everything that needs you, one section at a time. Each task carries
// its own action; a finished one leaves the list and a message confirms it at the bottom.

type Notify = (text: string, tone?: "good" | "bad") => void;
type Ctx = { groups: CategoryGroup[]; notify: Notify; finish: (key: string, text: string) => void };

/** What to do in each section, in plain words, shown above its list. */
const HOW: Record<string, string> = {
  categorize:
    "Pick a category for each merchant. With “Use for future lines too”, the app remembers it and categorizes the next ones on its own.",
  who: "Transfers that don't say who they're from or to. Choose the person (or add one), or a category such as Salary.",
  transfers:
    "Money moved between accounts and the app can't find the other side. Say what it was (the house, a loan, a person), or press “Other side isn't in the app” when it came from or went to an account you don't track. If that statement is just not uploaded yet, leave it: it pairs up on its own.",
  books:
    "Three kinds of loose ends. A statement to upload: the month isn't complete without it. An import to approve: a statement you uploaded that's waiting for you to check it. A bill not paid: something you told the app comes every month (rent, school, insurance) and no line paid it yet; open Bills and link the line that paid it, or change the bill if it changed. Each button takes you there.",
  loans: "Say Yes when the month's installment is paid; the balance updates from the loan's table.",
  values:
    "Values on Net worth that are old. Enter today's value, or stop counting it if you don't have it any more or it's the same money as another item.",
  suggestions:
    "Two kinds. A rule: you've given lines with the same text the same category several times; Save rule and future lines with that text get it on their own (see or delete rules in Settings → Rules). A bill: the same charge shows up every month; Add to bills and the app expects it monthly, warns when it's late or costs more, and counts it in the forecast. Not a bill or No: it won't ask again.",
  invoices:
    "Electronic invoices (SRI) count for the yearly personal expenses deduction once each says whose it is and what it was for. That's done on Taxes → Deductions.",
};

export default function TodoPage() {
  const q = useQuery({ queryKey: ["todo"], queryFn: fetchTodo });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const qc = useQueryClient();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const [note, setNote] = useState<{ text: string; tone: "good" | "bad" } | null>(null);
  const [gone, setGone] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!note) return;
    const t = setTimeout(() => setNote(null), 6000);
    return () => clearTimeout(t);
  }, [note]);

  const notify: Notify = (text, tone = "good") => setNote({ text, tone });
  const finish = (key: string, text: string) => {
    setGone((g) => new Set(g).add(key));
    notify(text);
    [
      "todo",
      "review",
      "transactions",
      "cashflow",
      "spending",
      "networth",
      "rules",
      "recurring",
      "people",
    ].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  };
  const ctx: Ctx = { groups: cats.data ?? [], notify, finish };

  const sections = (q.data?.sections ?? [])
    .map((s) => {
      const tasks = s.tasks.filter((t) => !gone.has(t.key));
      return { ...s, tasks, count: s.count - (s.tasks.length - tasks.length) };
    })
    .filter((s) => s.count > 0);
  const left = sections.reduce((n, s) => n + s.count, 0);
  const wanted = hash.replace("#", "");
  const current = sections.find((s) => s.key === wanted) ?? sections[0];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-4xl font-bold tracking-tight">To do</h1>
        <p className="mt-1 text-muted">Everything that needs you. Pick a list and work through it.</p>
      </header>
      {q.error && (
        <p role="alert" className="card border-danger-ink p-4 text-danger-ink">
          {(q.error as Error).message}
        </p>
      )}
      {q.isLoading && <p className="text-muted">Loading…</p>}
      {q.data && left === 0 && (
        <section className="card p-8 text-center">
          <h2 className="text-xl font-semibold">All clear</h2>
          <p className="mt-1 text-muted">Nothing needs you right now.</p>
        </section>
      )}
      {current && (
        <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <nav aria-label="Sections" className="min-w-0 lg:sticky lg:top-6 lg:self-start">
            <p className="mb-2 hidden text-sm text-muted lg:block">
              <span className="num font-display text-2xl font-bold text-ink">{left}</span> things left
            </p>
            <ul className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1 lg:overflow-visible">
              {sections.map((s) => {
                const on = s.key === current.key;
                return (
                  <li key={s.key} className="shrink-0">
                    <button
                      type="button"
                      aria-current={on ? "true" : undefined}
                      onClick={() => navigate({ hash: s.key }, { replace: true })}
                      className={`flex w-full items-center justify-between gap-3 rounded-[10px] px-3 py-2 text-left text-sm font-medium ${
                        on
                          ? "bg-nav-active text-nav-active-ink"
                          : "bg-ground text-ink hover:bg-surface lg:bg-transparent"
                      }`}
                    >
                      <span className="whitespace-nowrap">{s.title}</span>
                      <span
                        className={`num rounded-full px-2 text-xs font-bold ${on ? "bg-ground" : "bg-surface"}`}
                      >
                        {s.count}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
          <SectionView key={current.key} s={current} ctx={ctx} />
        </div>
      )}
      {note && (
        <p
          role="status"
          className={`fixed bottom-6 left-1/2 z-50 w-[min(32rem,calc(100%-2rem))] -translate-x-1/2 rounded-[14px] border p-4 text-sm font-medium shadow-lg ${
            note.tone === "bad"
              ? "border-danger-ink bg-danger-bg text-danger-ink"
              : "border-line bg-good-bg text-good-ink"
          }`}
        >
          {note.text}
        </p>
      )}
    </div>
  );
}

function SectionView({ s, ctx }: { s: TodoSection; ctx: Ctx }) {
  const more = s.count - s.tasks.length;
  return (
    <section aria-label={s.title} className="min-w-0 space-y-4">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight">
          {s.title} <span className="num text-muted">· {s.count}</span>
        </h2>
        <p className="mt-2 rounded-[10px] bg-info-bg p-3 text-sm text-info-ink">
          {HOW[s.key] ?? s.hint}
          {s.key === "transfers" && (
            <>
              {" "}
              <Link to="/transfers" className="font-semibold underline">
                Settle them all on Transfers to settle
              </Link>
              : pair them, say where the money went, or recategorize, several at once.
            </>
          )}
        </p>
      </div>
      <ul className="card divide-y divide-line">
        {s.tasks.map((t) => (
          <TaskRow key={t.key} t={t} ctx={ctx} />
        ))}
      </ul>
      {more > 0 && <p className="text-sm text-muted">And {more} more: they show here as you finish these.</p>}
    </section>
  );
}

function TaskRow({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  return (
    <li className="space-y-3 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate font-semibold" title={t.title}>
            {t.title}
          </p>
          <p className="text-sm text-muted">
            {t.detail}
            {typeof t.data.statement_file_id === "number" && (
              <>
                {" · "}
                <a
                  className="text-primary underline"
                  target="_blank"
                  rel="noreferrer"
                  href={statementPageUrl(t.data.statement_file_id, (t.data.page as number | null) ?? null)}
                >
                  statement
                </a>
              </>
            )}
          </p>
        </div>
        {t.amount !== null && (
          <span className={`num shrink-0 font-semibold ${Number(t.amount) > 0 ? "text-flow-in" : ""}`}>
            {money(t.amount)}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Action t={t} ctx={ctx} />
      </div>
    </li>
  );
}

function Action({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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

const GO: Record<string, string> = {
  statement: "Upload it",
  import: "Review the import",
  recurring: "See bills",
  balance: "Check it",
};

function Go({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="btn btn-secondary h-9 px-4 text-sm" to={to}>
      {children}
    </Link>
  );
}

function Always({ on, set, ok = true }: { on: boolean; set: (v: boolean) => void; ok?: boolean }) {
  if (!ok)
    return (
      <span className="text-xs text-muted">Only this line: the description is too general to remember.</span>
    );
  return (
    <label className="flex items-center gap-1.5 text-sm">
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} />
      Use for future lines too
    </label>
  );
}

function Categorize({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  const ok = t.data.rule_ok !== false;
  const [always, setAlways] = useState(ok);
  const suggested = (t.data.suggested_category_id as number | null) ?? "";
  const save = useMutation({
    mutationFn: (category_id: number) =>
      resolveMerchant({
        merchant_key: t.data.merchant_key as string,
        category_id,
        transaction_ids: t.data.transaction_ids as number[],
        save_rule: ok && always,
      }),
    onSuccess: (r) =>
      ctx.finish(
        t.key,
        `Categorized ${r.categorized} line${r.categorized === 1 ? "" : "s"}` +
          (r.rule_id ? `, saved a rule${r.also_by_rule ? ` (+${r.also_by_rule} more lines)` : ""}.` : "."),
      ),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  return (
    <>
      <div className="w-72 max-w-full">
        <CategoryPicker
          label={`Category for ${t.title}`}
          hideLabel
          groups={ctx.groups}
          value={suggested}
          placeholder="Choose a category"
          onChange={(id) => id !== "" && save.mutate(id)}
        />
      </div>
      <Always on={always} set={setAlways} ok={ok} />
    </>
  );
}

/** A line on a card kept for one purpose that doesn't look like it (ADR-074): it belongs (asked no
 * more), or give it its category. */
function Purpose({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
  const id = t.data.transaction_id as number;
  const fine = useMutation({
    mutationFn: () => dismissTodo(t.key),
    onSuccess: () => ctx.finish(t.key, `Kept as ${String(t.data.for)}'s.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const move = useMutation({
    mutationFn: async (category_id: number) => {
      await updateTransaction(id, { category_id });
      await dismissTodo(t.key);
    },
    onSuccess: () => ctx.finish(t.key, "Categorized."),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  return (
    <>
      <button type="button" className="btn btn-secondary h-9 px-4 text-sm" onClick={() => fine.mutate()}>
        It’s {String(t.data.for)}’s
      </button>
      <div className="w-64 max-w-full">
        <CategoryPicker
          label={`Category for ${t.title}`}
          hideLabel
          groups={ctx.groups}
          value={(t.data.category_id as number | null) ?? ""}
          placeholder="Not hers: choose a category"
          onChange={(c) => c !== "" && move.mutate(c)}
        />
      </div>
    </>
  );
}

function Who({ t, ctx, transfer = false }: { t: TodoTask; ctx: Ctx; transfer?: boolean }) {
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const ok = t.data.rule_ok !== false && Boolean(t.data.merchant_key);
  const [always, setAlways] = useState(ok);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const id = t.data.transaction_id as number;
  const kinds = new Map(ctx.groups.flatMap((g) => [g, ...g.children]).map((c) => [c.category_id, c.kind]));

  const person = useMutation({
    mutationFn: (counterparty: number) => setWho(id, counterparty),
    onSuccess: () => ctx.finish(t.key, "Saved who it is."),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const newPerson = useMutation({
    mutationFn: async () => {
      const p = await createPerson({ name: name.trim() });
      await setWho(id, p.counterparty_id);
      return p;
    },
    onSuccess: (p) => ctx.finish(t.key, `Added ${p.name} and saved who it is.`),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const category = useMutation({
    mutationFn: async (category_id: number) => {
      await updateTransaction(id, { category_id });
      // A move between accounts still has no other side: settle it, or it would ask again.
      if (transfer && kinds.get(category_id) === "transfer") await oneSidedTransfer(id);
      if (!ok || !always) return false;
      try {
        await createRule({
          pattern: t.data.merchant_key as string,
          match_type: "contains",
          category_id,
          priority: 50,
        });
        return true;
      } catch {
        return false; // a rule for it exists already: the line is still categorized
      }
    },
    onSuccess: (rule) =>
      ctx.finish(t.key, rule ? "Categorized, and saved a rule for next time." : "Categorized."),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
  const settle = useMutation({
    mutationFn: () => oneSidedTransfer(id),
    onSuccess: () => ctx.finish(t.key, "Done: it won't ask for the other side again."),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });

  if (adding)
    return (
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) newPerson.mutate();
        }}
      >
        <input
          className="field !w-56"
          aria-label="New person's name"
          placeholder="Name, e.g. Napoles Transport"
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
        />
        <button className="btn btn-primary h-9 px-4 text-sm" disabled={!name.trim() || newPerson.isPending}>
          Add and save
        </button>
        <button type="button" className="btn btn-quiet h-9 px-3 text-sm" onClick={() => setAdding(false)}>
          Cancel
        </button>
      </form>
    );
  return (
    <>
      <select
        className="field !w-48"
        aria-label={`Who for ${t.title}`}
        value=""
        onChange={(e) => {
          if (e.target.value === "new") setAdding(true);
          else if (e.target.value) person.mutate(Number(e.target.value));
        }}
      >
        <option value="">A person…</option>
        {(people.data ?? [])
          .filter((p) => p.is_active !== false)
          .map((p) => (
            <option key={p.counterparty_id} value={p.counterparty_id}>
              {p.name}
            </option>
          ))}
        <option value="new">+ New person…</option>
      </select>
      <span className="text-sm text-muted">or</span>
      <div className="w-64 max-w-full">
        <CategoryPicker
          label={`Category for ${t.title}`}
          hideLabel
          groups={ctx.groups}
          value=""
          placeholder="A category (e.g. Salary)…"
          onChange={(cid) => cid !== "" && category.mutate(cid)}
        />
      </div>
      {transfer && (
        <button
          type="button"
          className="btn btn-secondary h-9 px-3 text-sm"
          disabled={settle.isPending}
          onClick={() => settle.mutate()}
        >
          Other side isn't in the app
        </button>
      )}
      <Always on={always} set={setAlways} ok={ok} />
    </>
  );
}

function Value({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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

function useDismiss(t: TodoTask, ctx: Ctx, text: string) {
  return useMutation({
    mutationFn: () => dismissTodo(t.key),
    onSuccess: () => ctx.finish(t.key, text),
    onError: (e: Error) => ctx.notify(e.message, "bad"),
  });
}

function Suggestion({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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

function LoanPaid({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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

function AddBill({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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
