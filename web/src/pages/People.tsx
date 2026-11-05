import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createNote,
  createPerson,
  deleteNote,
  deletePerson,
  fetchAccounts,
  fetchBalanceSheet,
  fetchCategories,
  fetchNotes,
  fetchPeople,
  fetchPersonLines,
  matchNotes,
  updatePerson,
  type CategoryGroup,
  type Person,
  type TransferNote,
} from "../api";
import CategoryPicker from "../components/CategoryPicker";
import { localToday, money, showAmount } from "../money";

type Notify = (message: string, tone?: "good" | "bad") => void;

const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

const REFRESH = ["people", "notes", "transactions", "networth", "status", "review", "transfers"];

function useRefresh() {
  const qc = useQueryClient();
  return () => REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

/** People whose money passes through the household's accounts, and transfers told to the app
 * before their statement arrives (ADR-023). */
export default function PeoplePage() {
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const peopleQ = useQuery({ queryKey: ["people"], queryFn: fetchPeople });

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">People & transfers</h1>
      <p className="mt-2 text-lg text-muted">
        Statements often say only “TRANSFERENCIA”. Tell the app who a transfer was for, and it names and
        categorizes the line when the statement is read.
      </p>
      <p
        aria-live="polite"
        className={
          status
            ? `mt-4 rounded-2xl px-4 py-3 ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`
            : "sr-only"
        }
      >
        {status?.message ?? ""}
      </p>
      {cats.data && peopleQ.data && (
        <>
          <NoteForm groups={cats.data} people={peopleQ.data} notify={notify} />
          <Notes notify={notify} />
          <People groups={cats.data} people={peopleQ.data} notify={notify} />
        </>
      )}
      {(cats.error || peopleQ.error) && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load: {((cats.error ?? peopleQ.error) as Error).message}
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- a note
function NoteForm({ groups, people, notify }: { groups: CategoryGroup[]; people: Person[]; notify: Notify }) {
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
function Notes({ notify }: { notify: Notify }) {
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

function NoteRow({ n, onDelete }: { n: TransferNote; onDelete: () => void }) {
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

// ---------------------------------------------------------------- people
function People({ groups, people, notify }: { groups: CategoryGroup[]; people: Person[]; notify: Notify }) {
  const [adding, setAdding] = useState(false);
  return (
    <section className="mt-10" aria-labelledby="people-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="people-heading" className="font-display text-2xl font-bold">
          People
        </h2>
        {!adding && (
          <button className="btn btn-secondary" onClick={() => setAdding(true)}>
            Add a person
          </button>
        )}
      </div>
      <p className="mt-2 text-muted">
        Lines whose description contains one of a person’s texts get their name and category. With a balance
        on Debt & Net Worth, money received for them raises what you hold and money paid out for them lowers
        it.
      </p>
      {adding && <PersonForm groups={groups} notify={notify} onDone={() => setAdding(false)} />}
      <ul className="mt-4 space-y-3" aria-label="People">
        {people.map((p) => (
          <PersonCard key={p.counterparty_id} p={p} groups={groups} notify={notify} />
        ))}
      </ul>
    </section>
  );
}

function PersonForm({
  groups,
  notify,
  onDone,
  person,
}: {
  groups: CategoryGroup[];
  notify: Notify;
  onDone: () => void;
  person?: Person;
}) {
  const refresh = useRefresh();
  const sheet = useQuery({ queryKey: ["networth"], queryFn: fetchBalanceSheet });
  const [name, setName] = useState(person?.name ?? "");
  const [patterns, setPatterns] = useState(person?.patterns ?? "");
  const [category, setCategory] = useState<number | "">(person?.category_id ?? "");
  const [balance, setBalance] = useState<string>(
    person?.holding_id ? String(person.holding_id) : person ? "" : "new",
  );
  const [opening, setOpening] = useState("");
  const [asOf, setAsOf] = useState(localToday());
  const loans = (sheet.data?.items ?? []).filter((i) => i.holding_class === "personal_loan" && i.holding_id);
  const save = useMutation({
    mutationFn: () => {
      const common = {
        name: name.trim(),
        patterns: patterns.trim() || null,
        category_id: category === "" ? null : category,
      };
      if (person) {
        return updatePerson(person.counterparty_id, {
          ...common,
          holding_id: balance && balance !== "new" ? Number(balance) : null,
        });
      }
      return createPerson({
        ...common,
        holding_id: balance && balance !== "new" ? Number(balance) : null,
        new_balance: balance === "new",
        opening_balance: balance === "new" && opening.trim() ? opening.trim() : null,
        opening_as_of: balance === "new" ? asOf : null,
      });
    },
    onSuccess: (p) => {
      refresh();
      notify(`${p.name} saved${p.lines ? `: ${p.lines} lines are theirs` : ""}.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-4 rounded-2xl border border-line p-4"
      aria-label={person ? `Edit ${person.name}` : "New person"}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <label>
          <span className="label">Name</span>
          <input
            className="field w-full"
            required
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          <span className="label">Texts to find in statements, separated by ;</span>
          <input
            className="field w-full"
            maxLength={400}
            placeholder="RUBEN MIRANDA; NAPOLES TRANSPORT"
            value={patterns}
            onChange={(e) => setPatterns(e.target.value)}
          />
        </label>
        <CategoryPicker
          label="Their category"
          value={category}
          onChange={setCategory}
          groups={groups}
          allowCreate={false}
        />
        <label>
          <span className="label">Balance on Debt & Net Worth</span>
          <select className="field w-full" value={balance} onChange={(e) => setBalance(e.target.value)}>
            <option value="">None</option>
            {!person && <option value="new">New: “Holding for {name.trim() || "…"}”</option>}
            {loans.map((l) => (
              <option key={l.holding_id!} value={l.holding_id!}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        {balance === "new" && (
          <>
            <label>
              <span className="label">What you hold for them today (optional)</span>
              <input
                className="field w-full"
                inputMode="decimal"
                value={opening}
                onChange={(e) => setOpening(e.target.value)}
              />
            </label>
            <label>
              <span className="label">As of</span>
              <input
                type="date"
                className="field w-full"
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
              />
            </label>
          </>
        )}
      </div>
      <div className="mt-4 flex gap-3">
        <button className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function PersonCard({ p, groups, notify }: { p: Person; groups: CategoryGroup[]; notify: Notify }) {
  const refresh = useRefresh();
  const [editing, setEditing] = useState(false);
  const [open, setOpen] = useState(false);
  const lines = useQuery({
    queryKey: ["people", p.counterparty_id, "lines"],
    queryFn: () => fetchPersonLines(p.counterparty_id),
    enabled: open,
  });
  const remove = useMutation({
    mutationFn: () => deletePerson(p.counterparty_id),
    onSuccess: () => {
      refresh();
      notify(`${p.name} removed; their lines keep their categories.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  if (editing)
    return <PersonForm person={p} groups={groups} notify={notify} onDone={() => setEditing(false)} />;
  return (
    <li className={`rounded-2xl border border-line p-4 ${p.is_active ? "" : "opacity-60"}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="font-display text-xl font-bold">{p.name}</span>
        <span className="text-sm text-muted">
          {p.lines} lines · received {money(p.received)} · paid {money(p.paid)}
        </span>
      </div>
      <p className="mt-1 text-sm text-muted">
        {p.category_path ?? "No category"}
        {p.patterns && ` · finds “${p.patterns}”`}
        {p.holding_name && ` · balance: ${p.holding_name}`}
      </p>
      <div className="mt-3 flex flex-wrap gap-3">
        <button className="btn btn-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide lines" : "Show lines"}
        </button>
        <button className="btn btn-quiet" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          className="btn btn-quiet"
          onClick={() => {
            if (window.confirm(`Remove ${p.name}? Lines keep their categories.`)) remove.mutate();
          }}
        >
          Remove
        </button>
      </div>
      {open && (
        <ul className="mt-3 divide-y divide-line" aria-label={`Lines of ${p.name}`}>
          {(lines.data ?? []).map((l) => (
            <li key={l.transaction_id} className="flex flex-wrap items-baseline justify-between gap-x-3 py-1">
              <span>
                <span className="num">{day(l.txn_date)}</span>
                <span className="text-muted"> · {l.account_name ?? "—"}</span>
                <span className="block font-mono text-xs text-muted">
                  {l.description}
                  {l.notes && ` · ${l.notes}`}
                </span>
              </span>
              <span className="num">{showAmount(l.amount)}</span>
            </li>
          ))}
          {lines.data && !lines.data.length && <li className="py-1 text-muted">No lines yet.</li>}
        </ul>
      )}
    </li>
  );
}
