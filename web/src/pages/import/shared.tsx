import { type Statement } from "../../api";

export const OUTCOME = {
  stored: { label: "Saved", className: "pill-good" },
  duplicate: { label: "Already uploaded", className: "pill-muted" },
  rejected: { label: "Not saved", className: "pill-bad" },
} as const;

export const STATUS = {
  detected: { label: "Ready", className: "pill-good" },
  needs_account: { label: "Choose account", className: "bg-attention-bg text-attention-ink" },
  unknown_format: { label: "Unknown format", className: "bg-attention-bg text-attention-ink" },
} as const;

export const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export const monthOf = (s: Statement) => (s.period_end ?? s.period_start ?? s.uploaded_at).slice(0, 7);

export const oldestFirst = (a: Statement, b: Statement) =>
  (a.period_start ?? "9999").localeCompare(b.period_start ?? "9999") ||
  a.uploaded_at.localeCompare(b.uploaded_at);

export const monthName = (ym: string) =>
  new Date(`${ym}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });

/** Statements ready to read, and those read and waiting for approval grouped by the month they
 * end in, so a backlog goes through oldest first: read them all, then approve month by month. */
export function backlog(statements: Statement[]) {
  const unread = statements
    .filter((s) => s.status === "detected" && !s.batch && s.can_read)
    .sort(oldestFirst);
  const waiting = statements.filter((s) => s.batch?.status === "preview").sort(oldestFirst);
  const months = new Map<string, { ready: Statement[]; problems: Statement[] }>();
  for (const s of waiting) {
    const m = months.get(monthOf(s)) ?? { ready: [], problems: [] };
    (s.batch!.tieout_ok ? m.ready : m.problems).push(s);
    months.set(monthOf(s), m);
  }
  return { unread, months: [...months.entries()].sort(([a], [b]) => a.localeCompare(b)) };
}

/** Where a statement stands, for the list's filter. */
export type Standing = "to_read" | "waiting" | "problems" | "attention" | "loaded";

export const STANDING: Record<Standing, string> = {
  to_read: "Not read yet",
  waiting: "Waiting for approval",
  problems: "Doesn’t tie out",
  attention: "Needs you (account or format)",
  loaded: "Loaded",
};

export function standing(s: Statement): Standing {
  if (s.status !== "detected") return "attention";
  if (s.batch?.status === "approved") return "loaded";
  if (s.batch?.status === "preview") return s.batch.tieout_ok ? "waiting" : "problems";
  return s.can_read ? "to_read" : "attention";
}

export const NO_ACCOUNT = "none";

/** The statements a filter keeps: by account ("none" for not matched yet), standing and file name. */
export function filterStatements(
  statements: Statement[],
  f: { account: string; standing: Standing | ""; text: string },
): Statement[] {
  const text = f.text.trim().toLowerCase();
  return statements.filter(
    (s) =>
      (!f.account ||
        (f.account === NO_ACCOUNT
          ? s.accounts.length === 0
          : s.accounts.some((a) => String(a.account_id) === f.account))) &&
      (!f.standing || standing(s) === f.standing) &&
      (!text || s.file_name.toLowerCase().includes(text) || s.source_label.toLowerCase().includes(text)),
  );
}
