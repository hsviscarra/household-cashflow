import { type Account, TYPES, EVERY, type Notify, useRefresh } from "./shared";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchCategories,
  createTemplate,
  type TemplateType,
  type RecurringTemplate,
  updateTemplate,
  deleteTemplate,
} from "../../api";
import CategoryPicker from "../../components/CategoryPicker";
import { useState } from "react";
import { monthLong, money, monthShort } from "../../money";
import { Link } from "react-router-dom";

export function TemplateFields({
  value,
  set,
  accounts,
}: {
  value: Record<string, string>;
  set: (k: string, v: string) => void;
  accounts: Account[];
}) {
  const groups = useQuery({ queryKey: ["categories"], queryFn: fetchCategories }).data ?? [];
  return (
    <>
      <CategoryPicker
        label="Category"
        value={value.category_id ? Number(value.category_id) : ""}
        onChange={(id) => set("category_id", id === "" ? "" : String(id))}
        groups={groups}
        required
      />
      <label>
        <span className="label">Counts as</span>
        <select className="field" value={value.type} onChange={(e) => set("type", e.target.value)}>
          {TYPES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Account (optional)</span>
        <select
          className="field"
          value={value.account_id}
          onChange={(e) => set("account_id", e.target.value)}
        >
          <option value="">Any account</option>
          {accounts.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">Description contains (optional)</span>
        <input
          className="field font-mono"
          maxLength={200}
          value={value.match_pattern}
          onChange={(e) => set("match_pattern", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Repeats</span>
        <select
          className="field"
          value={value.every_months}
          onChange={(e) => set("every_months", e.target.value)}
        >
          {Object.entries(EVERY).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="label">On day (optional)</span>
        <input
          className="field num"
          type="number"
          min={1}
          max={31}
          step="1"
          value={value.due_day}
          onChange={(e) => set("due_day", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Tolerance %</span>
        <input
          className="field num"
          type="number"
          min={0}
          max={100}
          step="1"
          value={value.tolerance_pct}
          onChange={(e) => set("tolerance_pct", e.target.value)}
        />
      </label>
    </>
  );
}

export function TemplateForm({
  accounts,
  month,
  onDone,
  notify,
}: {
  accounts: Account[];
  month: string;
  onDone: () => void;
  notify: Notify;
}) {
  const refresh = useRefresh();
  const [v, setV] = useState<Record<string, string>>({
    name: "",
    category_id: "",
    type: "expense",
    amount: "",
    start_month: month,
    account_id: "",
    match_pattern: "",
    tolerance_pct: "10",
    every_months: "1",
    due_day: "",
    end_month: "",
  });
  const set = (k: string, val: string) => setV({ ...v, [k]: val });
  const save = useMutation({
    mutationFn: () =>
      createTemplate({
        every_months: Number(v.every_months),
        due_day: v.due_day ? Number(v.due_day) : null,
        end_month: v.end_month ? `${v.end_month}-01` : null,
        name: v.name.trim(),
        category_id: Number(v.category_id),
        type: v.type as TemplateType,
        amount: v.amount,
        start_month: `${v.start_month}-01`,
        account_id: v.account_id ? Number(v.account_id) : null,
        match_pattern: v.match_pattern.trim() || null,
        tolerance_pct: v.tolerance_pct || "10",
      }),
    onSuccess: (t) => {
      refresh();
      notify(`${t.name} added from ${monthLong(t.start_month)}. Generate a month to expect it.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <form
      className="mt-4 grid gap-3 rounded-2xl bg-surface p-4 md:grid-cols-4"
      aria-label="New template"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <label className="md:col-span-2">
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
        <span className="label">Amount each time</span>
        <input
          className="field num"
          required
          type="number"
          min={0.01}
          step="0.01"
          inputMode="decimal"
          value={v.amount}
          onChange={(e) => set("amount", e.target.value)}
        />
      </label>
      <label>
        <span className="label">First month</span>
        <input
          type="month"
          className="field"
          required
          value={v.start_month}
          onChange={(e) => set("start_month", e.target.value)}
        />
      </label>
      <label>
        <span className="label">Last month (optional)</span>
        <input
          type="month"
          className="field"
          value={v.end_month}
          onChange={(e) => set("end_month", e.target.value)}
        />
      </label>
      <TemplateFields value={v} set={set} accounts={accounts} />
      <div className="flex gap-2 md:col-span-4">
        <button
          className="btn btn-secondary"
          disabled={save.isPending || !v.name.trim() || !v.category_id || !v.amount}
        >
          Add template
        </button>
        <button type="button" className="btn btn-quiet" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function TemplateEditor({
  t,
  accounts,
  notify,
  onClose,
}: {
  t: RecurringTemplate;
  accounts: Account[];
  notify: Notify;
  onClose: () => void;
}) {
  const refresh = useRefresh();
  const [v, setV] = useState<Record<string, string>>({
    name: t.name,
    category_id: String(t.category_id),
    type: t.type,
    account_id: t.account_id ? String(t.account_id) : "",
    match_pattern: t.match_pattern ?? "",
    tolerance_pct: String(Number(t.tolerance_pct)),
    end_month: t.end_month?.slice(0, 7) ?? "",
    every_months: String(t.every_months ?? 1),
    due_day: t.due_day ? String(t.due_day) : "",
  });
  const set = (k: string, val: string) => setV({ ...v, [k]: val });
  const [confirm, setConfirm] = useState(false);
  const save = useMutation({
    mutationFn: (patch: Parameters<typeof updateTemplate>[1]) => updateTemplate(t.template_id, patch),
    onSuccess: (r) => {
      refresh();
      notify(`${r.name} saved.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const remove = useMutation({
    mutationFn: () => deleteTemplate(t.template_id),
    onSuccess: () => {
      refresh();
      notify(`${t.name} removed, with its months.`);
      onClose();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  return (
    <section className="mt-6 rounded-2xl bg-surface p-4 md:p-5" aria-label={`Template ${t.name}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-bold">{t.name}</h2>
        <button className="btn btn-quiet h-9 px-3" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="mt-1 text-muted">
        From {monthLong(t.start_month)}
        {t.end_month ? ` to ${monthLong(t.end_month)}` : ""} ·{" "}
        {t.amounts
          .map((a) => `${money(a.amount)} from ${monthShort(a.from_month)} ${a.from_month.slice(0, 4)}`)
          .join(", then ")}
        {t.source === "excel" ? " · from the Cash Flow sheet" : ""}
      </p>
      <form
        className="mt-4 grid gap-3 md:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({
            name: v.name.trim(),
            category_id: Number(v.category_id),
            type: v.type as TemplateType,
            account_id: v.account_id ? Number(v.account_id) : null,
            match_pattern: v.match_pattern.trim() || null,
            tolerance_pct: v.tolerance_pct || "10",
            end_month: v.end_month ? `${v.end_month}-01` : null,
            every_months: Number(v.every_months),
            due_day: v.due_day ? Number(v.due_day) : null,
          });
        }}
      >
        <label className="md:col-span-2">
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
          <span className="label">Last month (optional)</span>
          <input
            type="month"
            className="field"
            value={v.end_month}
            onChange={(e) => set("end_month", e.target.value)}
          />
        </label>
        <div />
        <TemplateFields value={v} set={set} accounts={accounts} />
        <div className="flex flex-wrap gap-2 md:col-span-4">
          <button className="btn btn-secondary" disabled={save.isPending}>
            Save {t.name}
          </button>
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => save.mutate({ is_active: !t.is_active })}
          >
            {t.is_active ? "Pause it" : "Resume it"}
          </button>
          {!confirm ? (
            <button type="button" className="btn btn-quiet" onClick={() => setConfirm(true)}>
              Remove…
            </button>
          ) : (
            <button
              type="button"
              className="btn bg-danger-bg text-danger-ink"
              onClick={() => remove.mutate()}
            >
              Remove {t.name} and its months
            </button>
          )}
        </div>
      </form>
      <p className="mt-3 text-sm text-muted">
        To change the amount, select a month in the grid: “this month only” or “from this month on”.{" "}
        <Link className="text-primary underline" to="/transactions">
          See the transactions
        </Link>
      </p>
    </section>
  );
}
