import { type MonthStatus } from "../../api";

/** "3 things missing" / "1 thing missing" / "Complete". */
export function summary(m: MonthStatus): string {
  if (m.complete) return "Complete";
  return `${m.items.length} ${m.items.length === 1 ? "thing" : "things"} missing`;
}

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
