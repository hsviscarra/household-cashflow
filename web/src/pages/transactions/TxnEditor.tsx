import {
  type Txn,
  fetchCategories,
  fetchHistory,
  updateTransaction,
  updateRule,
  splitTransaction,
  removeSplit,
} from "../../api";
import { useInvalidate, learnedMessage } from "./shared";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import CategoryPicker from "../../components/CategoryPicker";
import { LineKnown } from "./LineKnown";
import { UnlinkTransfer } from "./Cells";
import { num, money } from "../../money";

export function TxnEditor({ t, onDone }: { t: Txn; onDone: () => void }) {
  const invalidate = useInvalidate();
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  const [categoryId, setCategoryId] = useState<number | "">(t.category_id ?? "");
  const [notes, setNotes] = useState(t.notes ?? "");
  const [message, setMessage] = useState<{ text: string; undo?: () => void; bad?: boolean } | null>(null);
  const history = useQuery({
    queryKey: ["history", t.transaction_id],
    queryFn: () => fetchHistory(t.transaction_id),
  });
  const save = useMutation({
    mutationFn: (body: { category_id?: number; notes?: string | null }) =>
      updateTransaction(t.transaction_id, body),
    onSuccess: () => {
      invalidate();
      history.refetch();
    },
    onError: (e: Error) => setMessage({ text: e.message, bad: true }),
  });
  const previous = t.category_id;

  return (
    <div className="space-y-4">
      {!t.parts && (
        <form
          className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            const body: { category_id?: number; notes?: string | null } = {};
            if (categoryId !== "" && categoryId !== t.category_id) body.category_id = categoryId;
            if ((notes.trim() || null) !== t.notes) body.notes = notes.trim() || null;
            if (!Object.keys(body).length) return onDone();
            save.mutate(body, {
              onSuccess: (saved) =>
                setMessage(
                  saved.learned
                    ? learnedMessage(saved, () =>
                        updateRule(saved.learned!.rule_id, { is_active: false }).then(() => {
                          invalidate();
                          setMessage({ text: "Rule turned off. The lines keep their category." });
                        }),
                      )
                    : {
                        text: `Saved: ${saved.category_path ?? "no category"}.`,
                        undo:
                          body.category_id && previous
                            ? () =>
                                save.mutate(
                                  { category_id: previous },
                                  { onSuccess: () => setMessage({ text: "Change undone." }) },
                                )
                            : undefined,
                      },
                ),
            });
          }}
        >
          <CategoryPicker label="Category" value={categoryId} onChange={setCategoryId} groups={groups} />
          <label>
            <span className="label">Note</span>
            <input
              className="field"
              maxLength={1000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-secondary" disabled={save.isPending}>
            Save
          </button>
        </form>
      )}
      <div aria-live="polite" className="min-h-6 text-sm">
        {message && (
          <span className={message.bad ? "text-danger-ink" : "text-good-ink"}>
            {message.text}{" "}
            {message.undo && (
              <button type="button" className="font-semibold underline" onClick={message.undo}>
                Undo
              </button>
            )}
          </span>
        )}
      </div>

      <LineKnown
        t={t}
        onCategory={(id) => {
          setCategoryId(id);
          save.mutate(
            { category_id: id },
            {
              onSuccess: (saved) =>
                setMessage(
                  saved.learned
                    ? learnedMessage(saved, () =>
                        updateRule(saved.learned!.rule_id, { is_active: false }).then(() => {
                          invalidate();
                          setMessage({ text: "Rule turned off. The lines keep their category." });
                        }),
                      )
                    : { text: `Saved: ${saved.category_path ?? "no category"}.` },
                ),
            },
          );
        }}
      />

      <UnlinkTransfer t={t} />
      {!t.parent_transaction_id && !t.transfer_group_id && <SplitEditor t={t} />}

      <details>
        <summary className="cursor-pointer text-sm text-primary">History of this line</summary>
        {history.data && !history.data.length && (
          <p className="mt-2 text-sm text-muted">No changes since it was loaded.</p>
        )}
        {history.data && history.data.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm">
            {history.data.map((c) => (
              <li key={c.change_id}>
                <span className="num text-muted">{c.changed_at.slice(0, 16).replace("T", " ")}</span>{" "}
                {c.changed_by}: {c.column_name} {c.old_value ?? "—"} → {c.new_value ?? "—"}{" "}
                <span className="text-muted">({c.reason})</span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}

export type PartRow = { amount: string; categoryId: number | "" };

export function SplitEditor({ t }: { t: Txn }) {
  const invalidate = useInvalidate();
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  const size = Math.abs(num(t.amount));
  const sign = num(t.amount) < 0 ? -1 : 1;
  const [rows, setRows] = useState<PartRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const split = useMutation({
    mutationFn: (parts: PartRow[]) =>
      splitTransaction(
        t.transaction_id,
        parts.map((p) => ({
          amount: (sign * Number(p.amount)).toFixed(2),
          category_id: Number(p.categoryId),
        })),
      ),
    onSuccess: () => {
      setRows(null);
      invalidate();
    },
    onError: (e: Error) => setError(e.message),
  });
  const unsplit = useMutation({
    mutationFn: () => removeSplit(t.transaction_id),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  if (!rows)
    return (
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() =>
            setRows([
              { amount: size.toFixed(2), categoryId: t.category_id ?? "" },
              { amount: "", categoryId: "" },
            ])
          }
        >
          {t.parts ? "Change the split" : "Split across categories"}
        </button>
        {t.parts > 0 && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={unsplit.isPending}
            onClick={() => unsplit.mutate()}
          >
            Remove split
          </button>
        )}
        {error && <span className="text-danger-ink">{error}</span>}
      </div>
    );

  const assigned = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const left = Math.round((size - assigned) * 100) / 100;
  const ready = left === 0 && rows.every((r) => Number(r.amount) > 0 && r.categoryId !== "");
  const set = (i: number, patch: Partial<PartRow>) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <form
      className="space-y-3 rounded-2xl border border-line p-3"
      aria-label={`Split ${t.description}`}
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        if (ready) split.mutate(rows);
      }}
    >
      <p className="text-sm text-muted">
        Split <span className="num text-ink">{money(size)}</span> across categories. The line stays as loaded;
        its parts count instead.
      </p>
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[8rem_minmax(0,1fr)_auto] items-end gap-2">
          <label>
            <span className="label">Part {i + 1}</span>
            <input
              className="field num"
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={r.amount}
              onChange={(e) => set(i, { amount: e.target.value })}
            />
          </label>
          <CategoryPicker
            label={`Category of part ${i + 1}`}
            value={r.categoryId}
            onChange={(id) => set(i, { categoryId: id })}
            groups={groups}
          />
          <button
            type="button"
            className="btn btn-quiet h-11 px-3"
            aria-label={`Remove part ${i + 1}`}
            disabled={rows.length <= 2}
            onClick={() => setRows(rows.filter((_, j) => j !== i))}
          >
            ✕
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => setRows([...rows, { amount: left > 0 ? left.toFixed(2) : "", categoryId: "" }])}
        >
          Add a part
        </button>
        <span className={`num ${left === 0 ? "text-good-ink" : "text-attention-ink"}`} aria-live="polite">
          {left === 0
            ? "Fully assigned"
            : left > 0
              ? `${money(left)} left to assign`
              : `${money(-left)} too much`}
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-secondary" disabled={!ready || split.isPending}>
          Save split
        </button>
        <button type="button" className="btn btn-quiet" onClick={() => setRows(null)}>
          Cancel
        </button>
      </div>
      {error && <p className="text-danger-ink">{error}</p>}
    </form>
  );
}
