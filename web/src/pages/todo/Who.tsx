import {
  type TodoTask,
  resolveMerchant,
  dismissTodo,
  updateTransaction,
  fetchPeople,
  setWho,
  createPerson,
  oneSidedTransfer,
  createRule,
} from "../../api";
import { type Ctx } from "./shared";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import CategoryPicker from "../../components/CategoryPicker";

export function Always({ on, set, ok = true }: { on: boolean; set: (v: boolean) => void; ok?: boolean }) {
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

export function Categorize({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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
  const name =
    suggested === ""
      ? null
      : (ctx.groups.flatMap((g) => [g, ...g.children]).find((c) => c.category_id === suggested)?.name ??
        null);
  return (
    <>
      {suggested !== "" && name && (
        <button
          type="button"
          className="btn btn-primary h-9 px-4 text-sm"
          disabled={save.isPending}
          onClick={() => save.mutate(suggested)}
        >
          Accept: {name}
        </button>
      )}
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
export function Purpose({ t, ctx }: { t: TodoTask; ctx: Ctx }) {
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

export function Who({ t, ctx, transfer = false }: { t: TodoTask; ctx: Ctx; transfer?: boolean }) {
  const people = useQuery({ queryKey: ["people"], queryFn: fetchPeople });
  const ok = t.data.rule_ok !== false && Boolean(t.data.merchant_key);
  const [always, setAlways] = useState(ok);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const id = t.data.transaction_id as number;
  const kinds = new Map(ctx.groups.flatMap((g) => [g, ...g.children]).map((c) => [c.category_id, c.kind]));

  // The category the line has now: keeping it is one press, not choosing it again.
  const keep = transfer
    ? (ctx.groups.flatMap((g) => [g, ...g.children]).find((c) => c.category_id === t.data.category_id)
        ?.name ?? null)
    : null;

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
          {keep ? `Keep as ${keep}: other side isn't in the app` : "Other side isn't in the app"}
        </button>
      )}
      <Always on={always} set={setAlways} ok={ok} />
    </>
  );
}
