import { day } from "./shared";
import { type AccountTimeline } from "../../api";
import { Link } from "react-router-dom";

export const range = (a: string, b: string) => `${day(a)} – ${day(b)}`;

export const ordinal = (n: number) =>
  `${n}${n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th"}`;

export const STMT: Record<
  "loaded" | "waiting" | "problems" | "not_read" | "synced",
  { label: string; look: string }
> = {
  loaded: { label: "Loaded", look: "pill-good" },
  synced: { label: "Bank sync", look: "pill-good" },
  waiting: { label: "Waiting for approval", look: "bg-attention-bg text-attention-ink" },
  problems: { label: "Doesn’t tie out", look: "pill-bad" },
  not_read: { label: "Not read yet", look: "pill-muted" },
};

/** "Download the statement closing Jul 3, 2026", or a plain upload prompt when the cycle isn't
 * known yet (no statement next to the gap). */
export function downloadText(g: { closes?: string[] }): string {
  const closes = g.closes ?? [];
  if (!closes.length) return "No statement: upload it";
  return `Download the ${closes.length === 1 ? "statement" : "statements"} closing ${closes.map(day).join(" and ")}`;
}

/** "Missing" gaps (not the current cycle): what to download from the bank. */
export function missingGaps(a: AccountTimeline) {
  return a.gaps.filter((g) => !g.due);
}

/** Each account's statements in order, with the days no statement covers between them: the
 * dates to download. The current cycle isn't missing until the bank issues its statement. */
export function StatementPeriods({ accounts }: { accounts: AccountTimeline[] }) {
  return (
    <div className="mt-8">
      <h2 className="font-display text-2xl font-bold">Statement periods</h2>
      <p className="mt-1 text-muted">
        Every statement each account has, oldest first, and the exact days none covers. Cards and Bank of
        America don’t follow calendar months, so a month needs the statements on both sides of it.
      </p>
      <ul className="mt-3 space-y-3" aria-label="Statement periods by account">
        {accounts.map((a) => {
          const missing = missingGaps(a);
          const items = [
            ...a.statements.map((s) => ({ kind: "stmt" as const, start: s.start, s })),
            ...a.gaps.map((g) => ({ kind: "gap" as const, start: g.start, g })),
          ].sort((x, y) => x.start.localeCompare(y.start));
          const headingId = `periods-${a.account_id}`;
          return (
            <li key={a.account_id} className="rounded-2xl border border-line" aria-labelledby={headingId}>
              <details open={missing.length > 0} className="group p-4">
                <summary className="flex cursor-pointer list-none flex-wrap items-baseline justify-between gap-2">
                  <span>
                    <span
                      aria-hidden
                      className="mr-2 inline-block text-muted transition-transform group-open:rotate-90"
                    >
                      ›
                    </span>
                    <span id={headingId} className="font-semibold">
                      {a.name}
                    </span>
                    <span className="text-sm text-muted">
                      {a.start_day ? ` · statements start on the ${ordinal(a.start_day)}` : ""}
                      {a.closed_on ? ` · closed ${day(a.closed_on)}` : ""}
                    </span>
                  </span>
                  <span
                    className={`pill ${missing.length ? "bg-attention-bg text-attention-ink" : "pill-good"}`}
                  >
                    {missing.length
                      ? `${missing.length} ${missing.length === 1 ? "gap" : "gaps"} to fill`
                      : "No gaps"}
                  </span>
                </summary>
                <ol className="mt-3 divide-y divide-line text-sm">
                  {items.map((it) =>
                    it.kind === "stmt" ? (
                      <li
                        key={`s${it.s.statement_file_id}`}
                        className="flex flex-wrap items-center justify-between gap-2 py-1.5"
                      >
                        <span className="num">{range(it.s.start, it.s.end)}</span>
                        <span className="flex items-center gap-2">
                          <span className="hidden max-w-56 truncate text-muted md:inline">
                            {it.s.file_name}
                          </span>
                          {it.s.batch_id ? (
                            <Link
                              to={`/import/batches/${it.s.batch_id}`}
                              className={`pill ${STMT[it.s.state].look}`}
                            >
                              {STMT[it.s.state].label}
                            </Link>
                          ) : (
                            <Link to="/import" className={`pill ${STMT[it.s.state].look}`}>
                              {STMT[it.s.state].label}
                            </Link>
                          )}
                        </span>
                      </li>
                    ) : it.g.due ? (
                      <li
                        key={`g${it.g.start}`}
                        className="flex flex-wrap items-center justify-between gap-2 py-1.5"
                      >
                        <span className="num text-muted">{range(it.g.start, it.g.end)}</span>
                        <span className="text-muted">
                          Current cycle: the bank issues it around {day(it.g.due)}
                        </span>
                      </li>
                    ) : (
                      <li
                        key={`g${it.g.start}`}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-attention-bg px-2 py-1.5 text-attention-ink"
                      >
                        <span className="num font-semibold">{range(it.g.start, it.g.end)}</span>
                        <span className="text-right">
                          <Link to="/import" className="font-semibold underline-offset-2 hover:underline">
                            {downloadText(it.g)}
                          </Link>
                          {(it.g.files?.length ?? 0) > 0 && (
                            <span className="block font-mono text-xs">{it.g.files!.join(", ")}</span>
                          )}
                        </span>
                      </li>
                    ),
                  )}
                  {items.length === 0 && <li className="py-1.5 text-muted">No statements yet.</li>}
                </ol>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
