import { type SpendFilter, type Spending } from "../../api";
import { num, money, parts, localToday, monthLong } from "../../money";

export type Drill = { title: string; filter: SpendFilter; from: "category" | "who" | "merchants" } | null;

/** "+12% (+120.00)" / "−5% (−40.00)" / "new" / "—" — the change from a previous amount. */
export function change(now: string | number, before: string | number): string {
  const a = num(now);
  const b = num(before);
  if (!b) return a ? "new" : "—";
  const d = a - b;
  const pctText = `${d >= 0 ? "+" : "−"}${Math.abs(Math.round((d / b) * 100))}%`;
  return `${pctText} (${d >= 0 ? "+" : "−"}${money(Math.abs(d))})`;
}

/** "9% more than August" / "5% less than September 2025" / "the same as …". */
export function compareWords(now: string | number, before: string | number, label: string): string | null {
  const a = num(now);
  const b = num(before);
  if (!b) return null;
  const p = Math.round(((a - b) / b) * 100);
  if (p === 0) return `about the same as ${label}`;
  return `${Math.abs(p)}% ${p > 0 ? "more" : "less"} than ${label}`;
}

export const prevMonth = (iso: string) => {
  const { year, month } = parts(iso);
  return month === 1 ? `${year - 1}-12-01` : `${year}-${String(month - 1).padStart(2, "0")}-01`;
};

export const yearAgo = (iso: string) => `${parts(iso).year - 1}${iso.slice(4)}`;

export function headline(s: Spending, today: string = localToday()): string {
  if (s.source === "none") return "Spending";
  if (s.month.slice(0, 7) === today.slice(0, 7)) {
    // The month isn't over: comparing part of it with whole months would mislead.
    const day = Number(today.slice(8, 10));
    return `So far in ${monthLong(s.month)} (day ${day}) you spent ${money(s.total.amount)}.`;
  }
  const words = [
    compareWords(s.total.amount, s.total.prev, monthLong(prevMonth(s.month)).split(" ")[0]),
    compareWords(s.total.amount, s.total.last_year, monthLong(yearAgo(s.month))),
  ].filter(Boolean);
  return `In ${monthLong(s.month)} you spent ${money(s.total.amount)}${words.length ? `: ${words.join(", ")}` : ""}.`;
}
