import {
  type SheetItem,
  fetchCategories,
  fetchTemplates,
  type HoldingClass,
  updateHolding,
  createHolding,
  deleteHolding,
} from "../../api";
import { type Notify, useRefresh, today, CLASSES } from "./shared";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { categoryOptions } from "../../categories";

export function HoldingForm({
  item,
  notify,
  onDone,
}: {
  item?: SheetItem;
  notify: Notify;
  onDone: () => void;
}) {
  const refresh = useRefresh();
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const templates = useQuery({ queryKey: ["recurring", "templates"], queryFn: fetchTemplates });
  const [v, setV] = useState<Record<string, string>>({
    name: item?.name ?? "",
    holding_class: item?.holding_class ?? "property",
    side: item?.side ?? "asset",
    value: "",
    as_of: today(),
    target_amount: item?.purchase?.target ?? "",
    installment: item?.purchase?.installment ?? "",
    full_price: item?.purchase?.full_price ?? "",
    category_id: item?.category_id ? String(item.category_id) : "",
    recurring_template_id: item?.recurring_template_id ? String(item.recurring_template_id) : "",
    notes: item?.notes ?? "",
  });
  const [confirm, setConfirm] = useState(false);
  const set = (k: string, val: string) => setV({ ...v, [k]: val });
  const cls = v.holding_class as HoldingClass;
  const orNull = (x: string) => (x.trim() ? x.trim() : null);
  const body = {
    name: v.name.trim(),
    holding_class: cls,
    side: cls === "other" ? (v.side as "asset" | "liability") : null,
    target_amount: cls === "purchase" ? orNull(v.target_amount) : null,
    installment: cls === "purchase" ? orNull(v.installment) : null,
    full_price: cls === "purchase" ? orNull(v.full_price) : null,
    category_id: cls === "purchase" && v.category_id ? Number(v.category_id) : null,
    recurring_template_id: cls === "loan" && v.recurring_template_id ? Number(v.recurring_template_id) : null,
    notes: orNull(v.notes),
  };
  const save = useMutation({
    mutationFn: () =>
      item
        ? updateHolding(item.holding_id!, body)
        : createHolding({ ...body, value: orNull(v.value), as_of: v.value ? v.as_of : null }),
    onSuccess: () => {
      refresh();
      notify(item ? `${body.name} saved.` : `${body.name} added.`);
      onDone();
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const pause = useMutation({
    mutationFn: () => updateHolding(item!.holding_id!, { is_active: !item!.is_active }),
    onSuccess: () => {
      refresh();
      notify(item!.is_active ? `${item!.name} paused: not counted.` : `${item!.name} counted again.`);
      onDone();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteHolding(item!.holding_id!),
    onSuccess: () => {
      refresh();
      notify(`${item!.name} removed.`);
      onDone();
    },
  });
  const options = cats.data ? categoryOptions(cats.data) : [];
  return (
    <form
      className="mt-3 grid gap-3 rounded-2xl bg-surface p-4 md:grid-cols-4"
      aria-label={item ? `Edit ${item.name}` : "Add something you own or owe"}
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
      <label className="md:col-span-2">
        <span className="label">What it is</span>
        <select
          className="field"
          value={v.holding_class}
          onChange={(e) => set("holding_class", e.target.value)}
        >
          {CLASSES.filter((c) => c.id !== "card" || item?.holding_class === "card").map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      {cls === "other" && (
        <label>
          <span className="label">You</span>
          <select className="field" value={v.side} onChange={(e) => set("side", e.target.value)}>
            <option value="asset">own it</option>
            <option value="liability">owe it</option>
          </select>
        </label>
      )}
      {!item && (
        <>
          <label>
            <span className="label">{cls === "purchase" ? "Paid so far" : "Value"}</span>
            <input
              className="field num"
              type="number"
              min={0}
              step="0.01"
              inputMode="decimal"
              value={v.value}
              onChange={(e) => set("value", e.target.value)}
            />
          </label>
          <label>
            <span className="label">Value on</span>
            <input
              className="field"
              type="date"
              value={v.as_of}
              onChange={(e) => set("as_of", e.target.value)}
            />
          </label>
          <p className="text-sm text-muted md:col-span-2 md:self-end">
            Use the date you bought it (or took the loan) so past months include it.
          </p>
        </>
      )}
      {cls === "purchase" && (
        <>
          <Money
            label="Down payment to pay"
            value={v.target_amount}
            onChange={(x) => set("target_amount", x)}
          />
          <Money label="Each installment" value={v.installment} onChange={(x) => set("installment", x)} />
          <Money label="Full price" value={v.full_price} onChange={(x) => set("full_price", x)} />
          <label>
            <span className="label">Payments’ category (optional)</span>
            <select
              className="field"
              value={v.category_id}
              onChange={(e) => set("category_id", e.target.value)}
            >
              <option value="">None</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      {cls === "loan" && (
        <label className="md:col-span-2">
          <span className="label">Monthly payment (recurring item, optional)</span>
          <select
            className="field"
            value={v.recurring_template_id}
            onChange={(e) => set("recurring_template_id", e.target.value)}
          >
            <option value="">None</option>
            {(templates.data ?? []).map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="md:col-span-4">
        <span className="label">Note (optional)</span>
        <input
          className="field"
          maxLength={400}
          value={v.notes}
          onChange={(e) => set("notes", e.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2 md:col-span-4">
        <button className="btn btn-secondary" disabled={save.isPending || !v.name.trim()}>
          {item ? "Save" : "Add"}
        </button>
        {item && (
          <>
            <button type="button" className="btn btn-quiet" onClick={() => pause.mutate()}>
              {item.is_active ? "Pause (don’t count it)" : "Count it again"}
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
                Remove {item.name} and its values
              </button>
            )}
          </>
        )}
      </div>
    </form>
  );
}

export function Money({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label>
      <span className="label">{label}</span>
      <input
        className="field num"
        type="number"
        min={0}
        step="0.01"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
