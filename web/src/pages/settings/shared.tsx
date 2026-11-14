import { type CategoryKind, type MatchType } from "../../api";
import { type ReactNode } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";

export const KIND_LABEL: Record<CategoryKind, string> = {
  income: "Income",
  expense: "Expenses",
  savings: "Savings and investing",
  debt: "Debt payments (loans, a house being paid off)",
  transfer: "Transfers (not counted as spending)",
};

export const MATCH_LABEL: Record<MatchType, string> = {
  contains: "contains",
  starts_with: "starts with",
  regex: "regex",
};

export const ACCOUNT_KIND_LABEL = { checking: "Checking", savings: "Savings", credit_card: "Credit card" };

export type Notify = (message: string, tone?: "good" | "bad") => void;

// ---------------- shared bits ----------------
export function Loading({ what, error }: { what: string; error: unknown }) {
  if (error)
    return (
      <p className="rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
        Could not load {what}: {(error as Error).message}. Check that the database is connected and reload the
        page.
      </p>
    );
  return <p className="text-muted">Loading {what}…</p>;
}

export function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl bg-surface p-4 md:p-6">{children}</div>;
}

export function useSave<A, R>(fn: (a: A) => Promise<R>, keys: string[][], notify: Notify) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })),
    onError: (e: Error) => notify(e.message, "bad"),
  });
}

export function Swatch({ color }: { color: string | null }) {
  return (
    <span
      aria-hidden
      className="inline-block h-3.5 w-3.5 shrink-0 rounded-full border border-line"
      style={{ background: color ?? "var(--color-muted)" }}
    />
  );
}
