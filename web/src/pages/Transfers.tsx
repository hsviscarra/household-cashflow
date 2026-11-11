import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchCategories,
  fetchPeople,
  fetchTransferWorkbench,
  pairTransfer,
  settleOutside,
  statementPageUrl,
  updateTransaction,
  type CategoryGroup,
  type TransferBunch,
} from "../api";
import CategoryPicker from "../components/CategoryPicker";
import { money } from "../money";

// People & transfers → Transfers to settle (ADR-075): every transfer still missing its other side,
// bunched when the text and amount repeat, with three ways to settle it: pair it with a line in
// another account, say the other side is somewhere the app doesn't follow, or say it isn't a
// transfer at all and give it a category.

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

type Note = { text: string; bad?: boolean };

export default function TransfersPage() {
  const q = useQuery({ queryKey: ["transfers", "workbench"], queryFn: fetchTransferWorkbench });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const [note, setNote] = useState<Note | null>(null);
  const bunches = q.data?.bunches ?? [];
  const lines = bunches.reduce((n, b) => n + b.lines.length, 0);
  const places = [
    ...(q.data?.places ?? []),
    ...(people.data ?? []).filter((p) => p.is_active).map((p) => p.name),
  ];
  return (
    <section className="space-y-6">
      <header>
        <h1 className="font-display text-4xl font-bold tracking-tight">
          {q.data ? `${lines} ${lines === 1 ? "transfer" : "transfers"} to settle` : "Transfers to settle"}
        </h1>
        <p className="mt-1 max-w-3xl text-muted">
          A transfer needs its other side so it doesn’t count as spending or income. For each one: pair it
          with the line in your other account, say where the money went if that place isn’t in the app
          (Lauren’s flexible savings, Wise, an exchanger, a person), or say it isn’t a transfer and give it a
          category. Lines with the same text and amount are together, so one answer can settle them all.
        </p>
      </header>
      {note && (
        <p
          role="status"
          className={`rounded-[10px] p-3 text-sm ${note.bad ? "bg-danger-bg text-danger-ink" : "bg-good-bg text-good-ink"}`}
        >
          {note.text}
        </p>
      )}
      {q.error && <p className="text-danger-ink">{(q.error as Error).message}</p>}
      {!q.data && !q.error && <p className="text-muted">Loading…</p>}
      {q.data && !bunches.length && (
        <p className="card p-6 text-good-ink">Every transfer has its other side. Nothing to settle.</p>
      )}
      <ul className="space-y-4">
        {bunches.map((b) => (
          <li key={b.key}>
            <BunchCard b={b} places={places} groups={cats.data ?? []} notify={setNote} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function BunchCard({
  b,
  places,
  groups,
  notify,
}: {
  b: TransferBunch;
  places: string[];
  groups: CategoryGroup[];
  notify: (n: Note) => void;
}) {
  const qc = useQueryClient();
  const all = b.lines.map((l) => l.transaction_id);
  const [ticked, setTicked] = useState<Set<number>>(new Set(all));
  const [place, setPlace] = useState("");
  const chosen = all.filter((id) => ticked.has(id));
  const refresh = () =>
    ["transfers", "transactions", "cashflow", "todo", "status"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
  const fail = (e: Error) => notify({ text: e.message, bad: true });
  const pair = useMutation({
    mutationFn: ({ a, other }: { a: number; other: number }) => pairTransfer(a, other),
    onSuccess: () => {
      notify({ text: "Paired." });
      refresh();
    },
    onError: fail,
  });
  const outside = useMutation({
    mutationFn: () => settleOutside(chosen, place),
    onSuccess: (r) => {
      notify({ text: `Settled ${r.settled}: the other side is ${place}.` });
      refresh();
    },
    onError: fail,
  });
  const recat = useMutation({
    mutationFn: async (category_id: number) => {
      for (const id of chosen) await updateTransaction(id, { category_id });
      return chosen.length;
    },
    onSuccess: (n) => {
      notify({ text: `Categorized ${n} line${n === 1 ? "" : "s"}.` });
      refresh();
    },
    onError: fail,
  });
  const toggle = (id: number) =>
    setTicked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  return (
    <section aria-label={`${b.description} ${money(b.amount)}`} className="card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-lg font-bold">{b.description}</h2>
        <span className="num text-sm text-muted">
          {money(b.amount)} · {b.lines.length} {b.lines.length === 1 ? "line" : "lines"}
        </span>
      </div>
      <ul className="mt-3 divide-y divide-line text-sm">
        {b.lines.map((l) => (
          <li key={l.transaction_id} className="flex flex-wrap items-start gap-3 py-2">
            {b.lines.length > 1 && (
              <input
                type="checkbox"
                className="mt-1"
                aria-label={`Include ${day(l.txn_date)}`}
                checked={ticked.has(l.transaction_id)}
                onChange={() => toggle(l.transaction_id)}
              />
            )}
            <span className="min-w-40">
              <span className="num font-semibold">{day(l.txn_date)}</span>
              <span className="block text-muted">{l.account_name}</span>
            </span>
            <span className={`num w-28 text-right ${Number(l.amount) > 0 ? "text-flow-in" : ""}`}>
              {money(l.amount)}
            </span>
            <span className="min-w-0 flex-1">
              {l.candidates.length ? (
                <span className="flex flex-wrap gap-2">
                  {l.candidates.map((c) => (
                    <button
                      key={c.transaction_id}
                      type="button"
                      className="btn btn-secondary h-8 px-3 text-xs"
                      disabled={pair.isPending}
                      onClick={() => pair.mutate({ a: l.transaction_id, other: c.transaction_id })}
                      title={c.description}
                    >
                      Pair with {c.account_name} · {day(c.txn_date)}
                      {c.days ? ` (${c.days} ${c.days === 1 ? "day" : "days"} apart)` : ""}
                    </button>
                  ))}
                </span>
              ) : (
                <span className="text-muted">No line of the opposite amount in another account nearby.</span>
              )}
              {l.statement_file_id && (
                <a
                  className="mt-1 block text-xs text-primary underline"
                  target="_blank"
                  rel="noreferrer"
                  href={statementPageUrl(l.statement_file_id, null)}
                >
                  Open the statement
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-line pt-3">
        <span className="text-sm text-muted">
          {b.lines.length > 1 ? `For the ${chosen.length} ticked:` : "Or:"}
        </span>
        <label>
          <span className="label">The other side is</span>
          <select className="field w-60" value={place} onChange={(e) => setPlace(e.target.value)}>
            <option value="">Choose where…</option>
            {places.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!place || !chosen.length || outside.isPending}
          onClick={() => outside.mutate()}
        >
          Settle
        </button>
        <div className="w-72 max-w-full">
          <CategoryPicker
            label="It isn't a transfer: category"
            groups={groups}
            value=""
            placeholder="Choose a category…"
            onChange={(id) => id !== "" && chosen.length > 0 && recat.mutate(id)}
          />
        </div>
      </div>
    </section>
  );
}
