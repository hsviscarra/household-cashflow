import { type Notify, useRefresh, EVERY, day } from "./shared";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { fetchFoundBills, fetchSettings, type FoundBill, createTemplate, putSetting } from "../../api";
import { money } from "../../money";

export const DISMISSED = "bills_found_dismissed";

/** "Netflix.com" from "NETFLIX.COM": the name a found bill gets when added. */
export function billName(merchant: string): string {
  return merchant
    .toLowerCase()
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
    .slice(0, 100);
}

/** Charges that repeat and no recurring item covers yet, added with one click (ADR-043). */
export function FoundBills({ notify }: { notify: Notify }) {
  const qc = useQueryClient();
  const refresh = useRefresh();
  const found = useQuery({ queryKey: ["recurring", "found"], queryFn: fetchFoundBills });
  const me = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const raw = me.data?.settings[DISMISSED];
  const dismissed = Array.isArray(raw) ? (raw as string[]) : [];
  const shown = (found.data ?? []).filter((b) => !dismissed.includes(b.merchant));
  const add = useMutation({
    mutationFn: (b: FoundBill) =>
      createTemplate({
        name: billName(b.merchant),
        category_id: b.category_id,
        type: "expense",
        amount: b.amount,
        start_month: `${b.last_date.slice(0, 7)}-01`,
        account_id: b.account_id,
        person: b.person,
        match_pattern: b.match_pattern,
        every_months: b.every_months,
        due_day: b.due_day,
      }),
    onSuccess: (t) => {
      refresh();
      notify(`Added ${t.name} as a recurring item. Generate a month to see it in the grid.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  if (!shown.length) return null;
  const dismiss = (b: FoundBill) =>
    putSetting(DISMISSED, [...dismissed, b.merchant].slice(-200)).then(() =>
      qc.invalidateQueries({ queryKey: ["settings"] }),
    );
  return (
    <section aria-label="Found in your statements" className="card mt-6 space-y-3 p-5">
      <div>
        <h2 className="text-lg font-semibold">Found in your statements</h2>
        <p className="text-sm text-muted">
          These charges repeat with a similar amount and no recurring item covers them yet.
        </p>
      </div>
      <ul className="divide-y divide-line">
        {shown.map((b) => (
          <li key={b.merchant} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="font-semibold">
                {billName(b.merchant)} <span className="num font-normal">{money(b.amount)}</span>{" "}
                <span className="pill">{EVERY[String(b.every_months)]}</span>
              </p>
              <p className="text-sm text-muted">
                {b.category_path ?? "No category"}
                {b.account_name ? ` · ${b.account_name}` : ""} · around day {b.due_day} · {b.times} charges,
                last {day(b.last_date)}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="btn btn-primary h-9 px-4 text-sm"
                disabled={add.isPending}
                aria-label={`Add ${billName(b.merchant)} as a recurring item`}
                onClick={() => add.mutate(b)}
              >
                Add
              </button>
              <button
                className="btn btn-quiet h-9 px-4 text-sm"
                aria-label={`Not now ${billName(b.merchant)}`}
                onClick={() => void dismiss(b)}
              >
                Not now
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
