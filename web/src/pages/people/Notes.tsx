import {
  type CategoryGroup,
  type Person,
  fetchAccounts,
  createNote,
  fetchNotes,
  deleteNote,
  matchNotes,
  type TransferNote,
} from "../../api";
import { type Notify, useRefresh, day } from "./shared";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { localToday, money, showAmount } from "../../money";
import CategoryPicker from "../../components/CategoryPicker";

// ---------------------------------------------------------------- a note
export function NoteForm({
  groups,
  people,
  notify,
}: {
  groups: CategoryGroup[];
  people: Person[];
  notify: Notify;
}) {
  const refresh = useRefresh();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const [direction, setDirection] = useState<"sent" | "received">("sent");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(localToday());
  const [person, setPerson] = useState<number | "">("");
  const [account, setAccount] = useState<number | "">("");
  const [category, setCategory] = useState<number | "">("");
  const [description, setDescription] = useState("");
  const [share, setShare] = useState("");
  const save = useMutation({
    mutationFn: createNote,
    onSuccess: (n) => {
      refresh();
      setAmount("");
      setDescription("");
      setShare("");
      notify(
        n.transaction_id
          ? `Saved and matched to the ${day(n.line_date!)} line: ${n.line_description}.`
          : "Saved. It will be matched when the statement is read.",
      );
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-6 rounded-2xl border border-line p-4"
      aria-label="Tell the app about a transfer"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({
          txn_date: date,
          direction,
          amount: amount.trim(),
          counterparty_id: person === "" ? null : person,
          account_id: account === "" ? null : account,
          category_id: category === "" ? null : category,
          description: description.trim() || null,
          ...(person !== "" && share.trim() ? { share: share.trim() } : {}),
        });
      }}
    >
      <h2 className="font-display text-2xl font-bold">Tell the app about a transfer</h2>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <fieldset className="flex gap-2" aria-label="Direction">
          {(["sent", "received"] as const).map((d) => (
            <label key={d} className={`pill ${direction === d ? "pill-good" : "pill-muted"} cursor-pointer`}>
              <input
                type="radio"
                name="direction"
                className="sr-only"
                checked={direction === d}
                onChange={() => setDirection(d)}
              />
              {d === "sent" ? "I sent" : "I received"}
            </label>
          ))}
        </fieldset>
        <label>
          <span className="label">Amount</span>
          <input
            className="field w-36"
            inputMode="decimal"
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <label>
          <span className="label">Date</span>
          <input
            type="date"
            className="field w-44"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label>
          <span className="label">For whom</span>
          <select
            className="field w-48"
            value={person}
            onChange={(e) => setPerson(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Nobody in particular</option>
            {people
              .filter((p) => p.is_active)
              .map((p) => (
                <option key={p.counterparty_id} value={p.counterparty_id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
        <label>
          <span className="label">Account (optional)</span>
          <select
            className="field w-56"
            value={account}
            onChange={(e) => setAccount(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Any account</option>
            {(accounts.data ?? [])
              .filter((a) => a.is_active && a.kind !== "credit_card")
              .map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.name}
                </option>
              ))}
          </select>
        </label>
      </div>
      {person !== "" && (
        <label className="mt-4 block">
          <span className="label">Their share, if part of it is yours (optional)</span>
          <input
            className="field w-36"
            inputMode="decimal"
            value={share}
            onChange={(e) => setShare(e.target.value)}
          />
          <span className="mt-1 block text-sm text-muted">
            The line is split: their share in their category, the rest in the category below.
          </span>
        </label>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <CategoryPicker
          label={
            person !== "" && share.trim()
              ? "Category for your part"
              : "Category (optional: the person's is used)"
          }
          value={category}
          onChange={setCategory}
          groups={groups}
          allowCreate={false}
        />
        <label>
          <span className="label">What it was for</span>
          <input
            className="field w-full"
            maxLength={400}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
      </div>
      <button className="btn btn-primary mt-4" disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save the note"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------- the notes
export function Notes({ notify }: { notify: Notify }) {
  const refresh = useRefresh();
  const q = useQuery({ queryKey: ["notes"], queryFn: () => fetchNotes("all") });
  const remove = useMutation({
    mutationFn: deleteNote,
    onSuccess: () => {
      refresh();
      notify("Note deleted. A matched line keeps its category.");
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const again = useMutation({
    mutationFn: matchNotes,
    onSuccess: (r) => {
      refresh();
      notify(`Matched ${r.matched} ${r.matched === 1 ? "note" : "notes"}; named ${r.tagged} more lines.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const rows = q.data ?? [];
  return (
    <section className="mt-10" aria-labelledby="notes-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="notes-heading" className="font-display text-2xl font-bold">
          Transfer notes
        </h2>
        <button className="btn btn-quiet" disabled={again.isPending} onClick={() => again.mutate()}>
          Match again
        </button>
      </div>
      {!rows.length && <p className="mt-2 text-muted">No notes in the last four months.</p>}
      {!!rows.length && (
        <ul className="mt-4 divide-y divide-line rounded-2xl border border-line" aria-label="Transfer notes">
          {rows.map((n) => (
            <NoteRow key={n.note_id} n={n} onDelete={() => remove.mutate(n.note_id)} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function NoteRow({ n, onDelete }: { n: TransferNote; onDelete: () => void }) {
  const who = n.person ?? n.other_party ?? "Someone";
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-4 py-2">
      <span>
        <span className="num">{day(n.txn_date)}</span> · {who}
        {n.description && <span className="text-muted"> · {n.description}</span>}
        <span className="block text-xs text-muted">
          {n.transaction_id
            ? `Matched: ${day(n.line_date!)} ${n.line_description ?? ""}`
            : "Waiting for its statement"}
          {n.share && ` · their share ${money(n.share)}`}
          {n.category_path && ` · ${n.category_path}`}
          {n.account_name && ` · ${n.account_name}`}
          {n.source === "email" && " · from the bank's email"}
        </span>
      </span>
      <span className="flex items-baseline gap-3">
        <span className="num">{showAmount(n.amount)}</span>
        <button className="btn btn-quiet" aria-label={`Delete note ${n.note_id}`} onClick={onDelete}>
          Delete
        </button>
      </span>
    </li>
  );
}
