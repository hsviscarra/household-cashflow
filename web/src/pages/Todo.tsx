import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { fetchCategories, fetchTodo, statementPageUrl, type TodoSection, type TodoTask } from "../api";
import { money } from "../money";
import { type Notify, type Ctx } from "./todo/shared";
import { Action } from "./todo/Actions";

/** What to do in each section, in plain words, shown above its list. */
const HOW: Record<string, string> = {
  categorize:
    "Pick a category for each merchant. With “Use for future lines too”, the app remembers it and categorizes the next ones on its own.",
  who: "Transfers that don't say who they're from or to. Choose the person (or add one), or a category such as Salary.",
  transfers:
    "Money moved between accounts and the app can't find the other side. Say what it was (the house, a loan, a person), or press “Other side isn't in the app” when it came from or went to an account you don't track. If that statement is just not uploaded yet, leave it: it pairs up on its own.",
  books:
    "Three kinds of loose ends. A statement to upload: only for days that neither bank sync nor an emailed statement covered. An import to approve: a statement that's waiting for you to check it. A bill past its day: something that comes every month (rent, school, insurance) and no line paid it yet; lines pay bills on their own when a statement or the bank sync brings them. On Bills, press Change next to it to fix its day, skip this month or say it doesn't apply any more; to link the line that paid it, use Edit (year grid).",
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
        <p className="mt-1 text-sm text-muted">
          To check what's already categorized,{" "}
          <Link to="/transactions/categories" className="font-semibold text-primary underline">
            see every income and expense by category
          </Link>{" "}
          and move the lines that are wrong.
        </p>
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
