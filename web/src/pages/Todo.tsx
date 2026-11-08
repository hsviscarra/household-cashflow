import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  createRule,
  createTemplate,
  fetchCategories,
  fetchPeople,
  fetchTodo,
  resolveMerchant,
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

// To do (ADR-047): everything that needs you, in one list. Each task carries its own action, so
// most things are done right here; the rest open the page where they're fixed.

type Notify = (text: string, tone?: "good" | "bad") => void;

export default function TodoPage() {
  const q = useQuery({ queryKey: ["todo"], queryFn: fetchTodo });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const [note, setNote] = useState<{ text: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (text, tone = "good") => setNote({ text, tone });
  const groups = cats.data ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-4xl font-bold tracking-tight">To do</h1>
        <p className="mt-1 text-muted">
          Everything that needs you, in one place. Most things you can fix right here.
        </p>
      </header>
      {note && (
        <p
          role="status"
          className={`card p-3 text-sm ${note.tone === "bad" ? "border-warn text-warn" : "text-primary"}`}
        >
          {note.text}
        </p>
      )}
      {q.error && (
        <p role="alert" className="card border-warn p-4 text-warn">
          {(q.error as Error).message}
        </p>
      )}
      {q.isLoading && <p className="text-muted">Loading…</p>}
      {q.data && q.data.total === 0 && (
        <section className="card p-8 text-center">
          <h2 className="text-xl font-semibold">All clear</h2>
          <p className="mt-1 text-muted">Nothing needs you right now.</p>
        </section>
      )}
      {q.data && q.data.total > 0 && (
        <>
          <nav aria-label="Sections" className="flex flex-wrap gap-2">
            {q.data.sections.map((s) => (
              <a key={s.key} href={`#${s.key}`} className="btn btn-secondary h-8 gap-2 px-3 text-sm">
                {s.title}
                <span className="num rounded-full bg-surface px-2 text-xs font-bold">{s.count}</span>
              </a>
            ))}
          </nav>
          {q.data.sections.map((s) => (
            <Section key={s.key} s={s} groups={groups} notify={notify} />
          ))}
        </>
      )}
    </div>
  );
}

function Section({ s, groups, notify }: { s: TodoSection; groups: CategoryGroup[]; notify: Notify }) {
  const more = s.count - s.tasks.length;
  return (
    <section id={s.key} aria-label={s.title} className="card scroll-mt-6">
      <div className="border-b border-line p-5">
        <h2 className="text-lg font-semibold">
          {s.title} <span className="num text-muted">· {s.count}</span>
        </h2>
        <p className="text-sm text-muted">{s.hint}</p>
      </div>
      <ul className="divide-y divide-line">
        {s.tasks.map((t) => (
          <TaskRow key={t.key} t={t} groups={groups} notify={notify} />
        ))}
      </ul>
      {more > 0 && (
        <p className="border-t border-line p-4 text-sm text-muted">
          And {more} more: they show here as you finish these.
        </p>
      )}
    </section>
  );
}

function useDone(notify: Notify) {
  const qc = useQueryClient();
  return (text: string) => {
    notify(text);
    ["todo", "review", "transactions", "cashflow", "spending", "networth", "rules", "recurring"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
  };
}

function TaskRow({ t, groups, notify }: { t: TodoTask; groups: CategoryGroup[]; notify: Notify }) {
  return (
    <li className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <p className="truncate font-semibold" title={t.title}>
          {t.title}
          {t.amount !== null && <span className="num ml-2 font-normal">{money(t.amount)}</span>}
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
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Action t={t} groups={groups} notify={notify} />
      </div>
    </li>
  );
}

function Action({ t, groups, notify }: { t: TodoTask; groups: CategoryGroup[]; notify: Notify }) {
  switch (t.kind) {
    case "categorize":
      return <Categorize t={t} groups={groups} notify={notify} />;
    case "who":
      return <Who t={t} groups={groups} notify={notify} />;
    case "duplicate":
      return <Pause t={t} notify={notify} />;
    case "rule":
      return <SaveRule t={t} notify={notify} />;
    case "bill":
      return <AddBill t={t} notify={notify} />;
    default:
      return (
        <Link className="btn btn-secondary h-9 px-4 text-sm" to={t.link || "/"}>
          Open
        </Link>
      );
  }
}

function Categorize({ t, groups, notify }: { t: TodoTask; groups: CategoryGroup[]; notify: Notify }) {
  const done = useDone(notify);
  const [always, setAlways] = useState(true);
  const suggested = (t.data.suggested_category_id as number | null) ?? "";
  const save = useMutation({
    mutationFn: (category_id: number) =>
      resolveMerchant({
        merchant_key: t.data.merchant_key as string,
        category_id,
        transaction_ids: t.data.transaction_ids as number[],
        save_rule: always,
      }),
    onSuccess: (r) =>
      done(
        `Categorized ${r.categorized} line${r.categorized === 1 ? "" : "s"}` +
          (r.rule_id ? `, saved a rule${r.also_by_rule ? ` (+${r.also_by_rule} more lines)` : ""}.` : "."),
      ),
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <>
      <div className="w-64">
        <CategoryPicker
          label={`Category for ${t.title}`}
          hideLabel
          groups={groups}
          value={suggested}
          placeholder="Choose a category"
          onChange={(id) => id !== "" && save.mutate(id)}
        />
      </div>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
        Always
      </label>
    </>
  );
}

function Who({ t, groups, notify }: { t: TodoTask; groups: CategoryGroup[]; notify: Notify }) {
  const done = useDone(notify);
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const [always, setAlways] = useState(true);
  const id = t.data.transaction_id as number;
  const person = useMutation({
    mutationFn: (counterparty: number) => setWho(id, counterparty),
    onSuccess: () => done("Saved who it is."),
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const category = useMutation({
    mutationFn: async (category_id: number) => {
      const line = await updateTransaction(id, { category_id });
      if (always && t.data.merchant_key)
        await createRule({
          pattern: t.data.merchant_key as string,
          match_type: "contains",
          category_id,
          priority: 50,
        });
      return line;
    },
    onSuccess: () => done(always ? "Categorized, and saved a rule for next time." : "Categorized."),
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <>
      <select
        className="field !w-40"
        aria-label={`Who for ${t.title}`}
        value=""
        onChange={(e) => e.target.value && person.mutate(Number(e.target.value))}
      >
        <option value="">A person…</option>
        {(people.data ?? [])
          .filter((p) => p.is_active !== false)
          .map((p) => (
            <option key={p.counterparty_id} value={p.counterparty_id}>
              {p.name}
            </option>
          ))}
      </select>
      <span className="text-sm text-muted">or</span>
      <div className="w-56">
        <CategoryPicker
          label={`Category for ${t.title}`}
          hideLabel
          groups={groups}
          value=""
          placeholder="A category (e.g. Salary)…"
          onChange={(cid) => cid !== "" && category.mutate(cid)}
        />
      </div>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
        Always
      </label>
    </>
  );
}

function Pause({ t, notify }: { t: TodoTask; notify: Notify }) {
  const done = useDone(notify);
  const pause = useMutation({
    mutationFn: () => updateHolding(t.data.holding_id as number, { is_active: false }),
    onSuccess: () => done(`Paused ${t.title}; it no longer counts in net worth.`),
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <>
      <button className="btn btn-primary h-9 px-4 text-sm" disabled={pause.isPending} onClick={() => pause.mutate()}>
        Pause it
      </button>
      <Link className="btn btn-quiet h-9 px-4 text-sm" to={t.link}>
        Update instead
      </Link>
    </>
  );
}

function SaveRule({ t, notify }: { t: TodoTask; notify: Notify }) {
  const done = useDone(notify);
  const save = useMutation({
    mutationFn: () =>
      createRule({
        pattern: t.data.pattern as string,
        match_type: "contains",
        category_id: t.data.category_id as number,
        priority: 50,
        set_person: (t.data.person as Owner | null) ?? null,
      }),
    onSuccess: (r) => done(`Rule saved: ${r.pattern} → ${r.category_path}.`),
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <button className="btn btn-primary h-9 px-4 text-sm" disabled={save.isPending} onClick={() => save.mutate()}>
      Save rule
    </button>
  );
}

function AddBill({ t, notify }: { t: TodoTask; notify: Notify }) {
  const done = useDone(notify);
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
    onSuccess: (r) => done(`Added ${r.name} to your bills.`),
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <button className="btn btn-primary h-9 px-4 text-sm" disabled={add.isPending} onClick={() => add.mutate()}>
      Add to bills
    </button>
  );
}

