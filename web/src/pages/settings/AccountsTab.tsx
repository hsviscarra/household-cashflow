import { type AccountInput, fetchAccounts, createAccount, updateAccount, type Account } from "../../api";
import { type Notify, useSave, Loading, Panel, ACCOUNT_KIND_LABEL } from "./shared";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

// ---------------- accounts ----------------
export const EMPTY_ACCOUNT: AccountInput = {
  name: "",
  institution: "",
  kind: "checking",
  owner: "Hernan",
  country: "US",
  last4: null,
  is_active: true,
  closed_on: null,
  opened_on: null,
};

export const closedLabel = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export function AccountsTab({ notify }: { notify: Notify }) {
  const { data, error } = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const save = useSave(
    (a: { id: number | "new"; body: AccountInput }) =>
      a.id === "new" ? createAccount(a.body) : updateAccount(a.id, a.body),
    [["accounts"]],
    notify,
  );

  if (!data) return <Loading what="accounts" error={error} />;

  const submit = (id: number | "new", body: AccountInput) =>
    save.mutate(
      { id, body },
      {
        onSuccess: () => {
          setEditing(null);
          notify(id === "new" ? `Account added: ${body.name}.` : `Account saved: ${body.name}.`);
        },
      },
    );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        {editing !== "new" && (
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            Add account
          </button>
        )}
      </div>
      {editing === "new" && (
        <Panel>
          <AccountForm
            initial={EMPTY_ACCOUNT}
            submitLabel="Add account"
            busy={save.isPending}
            onCancel={() => setEditing(null)}
            onSubmit={(body) => submit("new", body)}
          />
        </Panel>
      )}
      <ul className="space-y-3">
        {data.map((a) => (
          <li key={a.account_id}>
            <Panel>
              {editing === a.account_id ? (
                <AccountForm
                  initial={a}
                  submitLabel="Save account"
                  busy={save.isPending}
                  onCancel={() => setEditing(null)}
                  onSubmit={(body) => submit(a.account_id, body)}
                />
              ) : (
                <AccountRow account={a} onEdit={() => setEditing(a.account_id)} />
              )}
            </Panel>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AccountRow({ account: a, onEdit }: { account: Account; onEdit: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div className="font-semibold">
          {a.name}
          {!a.is_active && <span className="pill pill-muted ml-2">Inactive</span>}
          {a.opened_on && <span className="pill pill-muted ml-2">Opened {closedLabel(a.opened_on)}</span>}
          {a.closed_on && <span className="pill pill-muted ml-2">Closed {closedLabel(a.closed_on)}</span>}
        </div>
        <div className="text-sm text-muted">
          {a.institution} · {ACCOUNT_KIND_LABEL[a.kind]} · {a.owner} · {a.country}
          {a.last4 ? <span className="num"> · •••• {a.last4}</span> : " · last 4 not set"}
        </div>
      </div>
      <button className="btn btn-secondary" onClick={onEdit} aria-label={`Edit ${a.name}`}>
        Edit
      </button>
    </div>
  );
}

export function AccountForm(props: {
  initial: AccountInput;
  submitLabel: string;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: AccountInput) => void;
}) {
  const [v, setV] = useState<AccountInput>({ ...EMPTY_ACCOUNT, ...props.initial });
  const set = <K extends keyof AccountInput>(k: K, value: AccountInput[K]) =>
    setV((old) => ({ ...old, [k]: value }));
  const last4Bad = !!v.last4 && !/^\d{4}$/.test(v.last4);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (last4Bad) return;
    const { name, institution, kind, owner, country, last4, is_active, closed_on, opened_on } = v;
    props.onSubmit({
      name: name.trim(),
      institution: institution.trim(),
      kind,
      owner,
      country,
      last4: last4 || null,
      is_active,
      closed_on: closed_on || null,
      opened_on: opened_on || null,
    });
  };

  return (
    <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-3">
      <label>
        <span className="label">Name</span>
        <input
          className="field"
          required
          maxLength={100}
          value={v.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Institution</span>
        <input
          className="field"
          required
          maxLength={100}
          value={v.institution}
          onChange={(e) => set("institution", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Type</span>
        <select
          className="field"
          value={v.kind}
          onChange={(e) => set("kind", e.target.value as AccountInput["kind"])}
        >
          {Object.entries(ACCOUNT_KIND_LABEL).map(([k, l]) => (
            <option key={k} value={k}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Owner</span>
        <select
          className="field"
          value={v.owner}
          onChange={(e) => set("owner", e.target.value as AccountInput["owner"])}
        >
          <option>Hernan</option>
          <option>Lauren</option>
          <option>Joint</option>
        </select>
      </label>
      <label>
        <span className="label">Country</span>
        <select
          className="field"
          value={v.country}
          onChange={(e) => set("country", e.target.value as AccountInput["country"])}
        >
          <option value="US">United States</option>
          <option value="EC">Ecuador</option>
        </select>
      </label>
      <label>
        <span className="label">Last 4 digits (never the full number)</span>
        <input
          className="field num"
          inputMode="numeric"
          maxLength={4}
          value={v.last4 ?? ""}
          aria-invalid={last4Bad}
          aria-describedby={last4Bad ? "last4-error" : undefined}
          onChange={(e) => set("last4", e.target.value)}
        />
        {last4Bad && (
          <span id="last4-error" className="mt-1 block text-sm text-danger-ink">
            Enter exactly four digits.
          </span>
        )}
      </label>
      <div className="md:col-span-3 md:max-w-xs">
        <label>
          <span className="label">Opened on (optional)</span>
          <input
            className="field"
            type="date"
            value={v.opened_on ?? ""}
            onChange={(e) => set("opened_on", e.target.value || null)}
            aria-describedby="opened-help"
          />
        </label>
        <span id="opened-help" className="mt-1 block text-sm text-muted">
          Data Status doesn't expect statements before this day.
        </span>
      </div>
      <div className="md:col-span-3 md:max-w-xs">
        <label>
          <span className="label">Closed or suspended on (optional)</span>
          <input
            className="field"
            type="date"
            value={v.closed_on ?? ""}
            onChange={(e) => set("closed_on", e.target.value || null)}
            aria-describedby="closed-help"
          />
        </label>
        <span id="closed-help" className="mt-1 block text-sm text-muted">
          Data Status stops expecting statements after this day; earlier ones still load.
        </span>
      </div>
      <label className="flex items-center gap-2 md:col-span-3">
        <input
          type="checkbox"
          className="h-5 w-5"
          checked={v.is_active}
          onChange={(e) => set("is_active", e.target.checked)}
        />
        Active (inactive accounts stay in history but are hidden from imports)
      </label>
      <div className="flex gap-2 md:col-span-3">
        <button type="submit" className="btn btn-primary" disabled={props.busy || last4Bad}>
          {props.submitLabel}
        </button>
        <button type="button" className="btn btn-quiet" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
