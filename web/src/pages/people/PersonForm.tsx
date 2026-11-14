import {
  type CategoryGroup,
  type Person,
  fetchBalanceSheet,
  updatePerson,
  createPerson,
  fetchPersonLines,
  deletePerson,
} from "../../api";
import { type Notify, useRefresh, day } from "./shared";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { localToday, money, showAmount } from "../../money";
import CategoryPicker from "../../components/CategoryPicker";
import { Link } from "react-router-dom";

// ---------------------------------------------------------------- people
export function People({
  groups,
  people,
  notify,
}: {
  groups: CategoryGroup[];
  people: Person[];
  notify: Notify;
}) {
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

export function PersonForm({
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

export function PersonCard({ p, groups, notify }: { p: Person; groups: CategoryGroup[]; notify: Notify }) {
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
        <Link to={`/transactions?cp=${p.counterparty_id}&months=12`} className="btn btn-quiet">
          In Transactions (12 months)
        </Link>
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
