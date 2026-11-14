import { type ReviewLine, statementPageUrl } from "../../api";
import { type LineSourceFn, fullDay, day } from "./shared";
import { useState } from "react";
import { showAmount } from "../../money";
import { useQuery } from "@tanstack/react-query";

/** One line of a merchant: the full date, the account, a link to the statement page and, on
 * request, everything the statement says about it (ADR-034). */
export function LineRow({
  ln,
  merchant,
  source,
  check,
}: {
  ln: ReviewLine;
  merchant: string;
  source?: LineSourceFn;
  check: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const posted = ln.post_date && ln.post_date !== ln.txn_date ? ln.post_date : null;
  return (
    <li className="py-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="flex items-baseline gap-2">
          {check}
          <span>
            <span className="num font-medium">{fullDay(ln.txn_date)}</span>
            {posted && <span className="text-muted"> · posted {day(posted)}</span>}
            <span className="text-muted">
              {" "}
              · {ln.account_name ?? "—"}
              {ln.person ? ` · ${ln.person}` : ""}
            </span>
            {ln.description !== merchant && (
              <span className="block font-mono text-xs text-muted">{ln.description}</span>
            )}
          </span>
        </span>
        <span className="num">{showAmount(ln.amount)}</span>
      </div>
      {(ln.statement_file_id || source) && (
        <div className="mt-0.5 flex flex-wrap gap-x-4 pl-7 text-xs">
          {ln.statement_file_id && (
            <a
              className="text-primary underline"
              href={statementPageUrl(ln.statement_file_id, ln.page)}
              target="_blank"
              rel="noreferrer"
            >
              Open the statement{ln.page ? `, page ${ln.page}` : ""}
            </a>
          )}
          {source && (
            <button
              type="button"
              className="text-primary underline"
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {open ? "Hide details" : "More details"}
            </button>
          )}
        </div>
      )}
      {open && source && <LineDetails id={ln.transaction_id} source={source} />}
    </li>
  );
}

export const SECTION: Record<string, string> = {
  payment: "Payment",
  purchase: "Purchase",
  fee: "Fee",
  interest: "Interest",
  credit: "Money in",
  debit: "Money out",
  transfer: "Transfer",
};

export function LineDetails({ id, source }: { id: number; source: LineSourceFn }) {
  const q = useQuery({ queryKey: ["line-source", source.scope, id], queryFn: () => source.fetch(id) });
  if (q.error) return <p className="mt-2 pl-7 text-xs text-danger-ink">{(q.error as Error).message}</p>;
  const d = q.data;
  if (!d) return <p className="mt-2 pl-7 text-xs text-muted">Reading the statement…</p>;
  const facts: [string, string | null][] = [
    ["Date", fullDay(d.txn_date)],
    ["Posted", d.post_date ? fullDay(d.post_date) : null],
    [
      "Account",
      d.account_name ? `${d.account_name}${d.account_last4 ? ` ····${d.account_last4}` : ""}` : null,
    ],
    ["Card", d.cardholder ? `····${d.cardholder}` : null],
    ["Kind on the statement", d.section ? (SECTION[d.section] ?? d.section) : null],
    ["Reference", d.pay_reference],
    ["Note", d.notes],
    [
      "Statement",
      d.file_name
        ? `${d.file_name}${d.period_start && d.period_end ? ` (${day(d.period_start)} to ${fullDay(d.period_end)})` : ""}`
        : null,
    ],
    ["Where", d.page ? `page ${d.page}, line ${d.line_no}` : null],
  ];
  return (
    <div
      className="mt-2 ml-7 space-y-3 rounded-xl bg-surface p-3 text-xs"
      aria-label={`Details of ${fullDay(d.txn_date)}`}
    >
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
        {facts
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
      {(d.note_from || d.note || d.note_person) && (
        <p className="rounded-lg bg-info-bg px-2 py-1.5">
          <strong>From the transfer email:</strong> {d.note_from ? `${d.note_from}` : ""}
          {d.note_person ? ` (${d.note_person})` : ""}
          {d.note ? ` · “${d.note}”` : ""}
        </p>
      )}
      {d.around.length > 0 && (
        <div>
          <p className="text-muted">
            On the statement (the line in bold, account and ID numbers cut to their last 4):
          </p>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-ground p-2 font-mono leading-relaxed whitespace-pre-wrap">
            {d.around.map((a) => (
              <span key={a.line_no} className={a.is_line ? "block font-bold text-ink" : "block text-muted"}>
                {a.text || " "}
              </span>
            ))}
          </pre>
        </div>
      )}
      {d.unreadable && (
        <p className="text-attention-ink">
          The statement file couldn’t be read to show the text around the line.
        </p>
      )}
      {!d.around.length && d.text && (
        <p>
          <span className="text-muted">On the statement: </span>
          <span className="font-mono">{d.text}</span>
        </p>
      )}
      {d.similar.length > 0 && (
        <div>
          <p className="text-muted">The same merchant before:</p>
          <ul className="mt-1 space-y-0.5" aria-label="The same merchant before">
            {d.similar.map((x, i) => (
              <li key={i}>
                {fullDay(x.txn_date)} · <span className="num">{showAmount(x.amount)}</span> →{" "}
                <strong>{x.category_path ?? "—"}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
