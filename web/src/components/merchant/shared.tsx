import { type LineSource } from "../../api";
import { num } from "../../money";

export type Notify = (message: string, tone?: "good" | "bad") => void;

/** Reads where a line came from; `scope` keeps loaded and staged lines apart in the cache. */
export type LineSourceFn = { scope: string; fetch: (id: number) => Promise<LineSource> };

// Views a categorized line can change: refreshed after every save.
export const REFRESH = ["review", "transactions", "cashflow", "rules", "batch", "batch-review"];

// "Likely" in confidenceLabel: what "Accept likely suggestions" takes.
export const LIKELY = 0.8;

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** "Tue, Oct 14, 2026": the full date, so a line can be found on the statement (ADR-034). */
export const fullDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

/** "likely 85%", "maybe 60%", "unsure 30%": the number plus a word, never color alone. */
export function confidenceLabel(confidence: string): string {
  const v = num(confidence);
  const word = v >= LIKELY ? "likely" : v >= 0.5 ? "maybe" : "unsure";
  return `${word}, ${Math.round(v * 100)}%`;
}
