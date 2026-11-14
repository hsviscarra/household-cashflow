import { type Txn, type Owner } from "../../api";
import { num } from "../../money";
import { useQueryClient } from "@tanstack/react-query";

/** The second time a merchant gets the same category by hand, the app saves the rule (ADR-079). */
export function learnedMessage(saved: Txn, undo: () => void): { text: string; undo: () => void } {
  const l = saved.learned!;
  const more = l.lines ? ` ${l.lines} more ${l.lines === 1 ? "line" : "lines"} got it too.` : "";
  return {
    text: `Saved, and learned: “${l.pattern}” now goes to ${saved.category_path ?? "that category"} by itself.${more}`,
    undo,
  };
}

export const SOURCE_LABEL: Record<string, string> = {
  statement: "Statement",
  excel_history: "Excel history",
  manual: "Manual",
};

export const HOW: Record<string, string> = {
  rule: "by rule",
  section: "from the statement",
  manual: "chosen",
  suggestion: "Claude, accepted",
  excel: "workbook",
  split: "split part",
  match: "matched transfer",
  invoice: "from its invoice's products",
};

export function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const OWNERS: Owner[] = ["Hernan", "Lauren", "Joint"];

// Columns shown until a person chooses (ADR-026, ADR-030); the description and the amount always show.
export const DEFAULT_COLUMNS = ["date", "account", "who", "category", "note"];

export type Filters = {
  q: string;
  todo: boolean;
  account: string | null;
  group: string | null;
  min: number | null;
  max: number | null;
  note: boolean;
};

export const group = (t: Txn) => t.category_path?.split(/\s[/›]\s/)[0] ?? null;

/** The filters: search (description, merchant, note, category, account or amount), needs a
 * category, account, category group, amount range (without sign) and has a note. */
export function keep(t: Txn, f: Filters) {
  if (f.todo && (t.parts || t.category_id)) return false;
  if (f.account && t.account_name !== f.account) return false;
  if (f.group && group(t) !== f.group) return false;
  const size = Math.abs(num(t.amount));
  if (f.min !== null && size < f.min) return false;
  if (f.max !== null && size > f.max) return false;
  if (f.note && !t.notes) return false;
  const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  const text = [t.description, t.merchant, t.notes, t.category_path, t.account_name, size.toFixed(2)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return words.every((w) => text.includes(w.replace(/[$,]/g, "")));
}

/** Kept for the tests and saved views of 0.42: search and "needs a category". */
export const matches = (t: Txn, q: string, todo: boolean) =>
  keep(t, { q, todo, account: null, group: null, min: null, max: null, note: false });

/** Lines that count: a split line counts through its parts. */
export const counted = (t: Txn) => !t.parts;

export const cell = (v: string | null | undefined) => {
  const text = v ?? "";
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

/** The lines shown, as CSV (the columns of the table, every one). */
export function toCsv(rows: Txn[], names: Map<number, string>) {
  const head = [
    "Date",
    "Posted",
    "Description",
    "Merchant",
    "Account",
    "Who",
    "Category",
    "Note",
    "Person",
    "Country",
    "Amount",
  ];
  const body = rows.map((t) =>
    [
      t.txn_date,
      t.post_date,
      t.description,
      t.merchant,
      t.account_name,
      t.person,
      t.category_path,
      t.notes,
      t.counterparty_id ? names.get(t.counterparty_id) : null,
      t.country,
      t.amount,
    ]
      .map(cell)
      .join(","),
  );
  return [head.join(","), ...body].join("\n");
}

export function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const PERIODS: Record<string, string> = {
  "1": "This month",
  "3": "3 months to it",
  "12": "12 months to it",
};

export function ordered(txns: Txn[]): Txn[] {
  const parts = new Map<number, Txn[]>();
  for (const t of txns)
    if (t.parent_transaction_id)
      parts.set(t.parent_transaction_id, [...(parts.get(t.parent_transaction_id) ?? []), t]);
  return txns
    .filter((t) => !t.parent_transaction_id)
    .flatMap((t) => [
      t,
      ...(parts.get(t.transaction_id) ?? []).sort((a, b) => a.transaction_id - b.transaction_id),
    ]);
}

export function useInvalidate() {
  const qc = useQueryClient();
  return () =>
    ["transactions", "review", "cashflow", "transfers"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
}

export const shortDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
