import { type Statement, readStatement, approveReady, approveBatch, type UploadResult } from "../../api";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { backlog, monthName, OUTCOME } from "./shared";
import { Link } from "react-router-dom";

export function BulkActions({ statements }: { statements: Statement[] }) {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const { unread, months } = backlog(statements);
  if (!unread.length && !months.length && !progress && !errors.length) return null;

  async function run(items: Statement[], verb: string, act: (s: Statement) => Promise<unknown>) {
    setBusy(true);
    setErrors([]);
    const failed: string[] = [];
    for (const [i, s] of items.entries()) {
      setProgress(`${verb} ${i + 1} of ${items.length}: ${s.file_name}`);
      try {
        await act(s);
      } catch (e) {
        failed.push(`${s.file_name}: ${(e as Error).message}`);
      }
    }
    setProgress(
      `${verb === "Reading" ? "Read" : "Approved"} ${items.length - failed.length} of ${items.length}.`,
    );
    setErrors(failed);
    setBusy(false);
    qc.invalidateQueries();
  }

  return (
    <section aria-label="Backlog" className="mt-6 rounded-2xl bg-ground p-4">
      <h3 className="font-display text-xl font-bold">Load the backlog, oldest first</h3>
      {unread.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <span>
            {unread.length} {unread.length === 1 ? "statement" : "statements"} to read.
          </span>
          <button
            className="btn btn-secondary h-9 px-4"
            disabled={busy}
            onClick={() => run(unread, "Reading", (s) => readStatement(s.statement_file_id))}
          >
            Read all ({unread.length})
          </button>
        </div>
      )}
      {months.some(([, m]) => m.ready.length > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            className="btn btn-primary h-9 px-4"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setErrors([]);
              setProgress("Approving every statement that ties out, oldest first…");
              try {
                const r = await approveReady();
                setProgress(
                  `Approved ${r.approved} ${r.approved === 1 ? "statement" : "statements"} (${r.loaded} lines).`,
                );
                setErrors(r.waiting.map((w) => `${w.file_name}: ${w.reason}`));
              } catch (e) {
                setErrors([(e as Error).message]);
              }
              setBusy(false);
              qc.invalidateQueries();
            }}
          >
            Approve all that tie out
          </button>
          <span className="text-sm text-muted">New uploads that tie out are approved on their own.</span>
        </div>
      )}
      {months.length > 0 && (
        <ul
          className="mt-3 divide-y divide-line rounded-2xl border border-line"
          aria-label="Waiting for approval"
        >
          {months.map(([ym, m]) => (
            <li key={ym} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <span>
                <strong>{monthName(ym)}</strong>: {m.ready.length} ready
                {m.problems.length > 0 && (
                  <>
                    {", "}
                    <span className="text-attention-ink">
                      {m.problems.length} {m.problems.length === 1 ? "doesn’t" : "don’t"} tie out
                    </span>{" "}
                    (
                    {m.problems.map((s, i) => (
                      <span key={s.statement_file_id}>
                        {i > 0 && ", "}
                        <Link className="text-primary underline" to={`/import/batches/${s.batch!.batch_id}`}>
                          {s.file_name}
                        </Link>
                      </span>
                    ))}
                    )
                  </>
                )}
              </span>
              {m.ready.length > 0 && (
                <button
                  className="btn btn-primary h-9 px-4"
                  disabled={busy}
                  onClick={() => run(m.ready, "Approving", (s) => approveBatch(s.batch!.batch_id))}
                >
                  Approve {m.ready.length}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <div aria-live="polite">
        {progress && <p className="mt-2 text-sm text-muted">{progress}</p>}
        {errors.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-sm text-danger-ink" aria-label="Problems">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        Approving in order lets each statement’s opening balance be checked against the previous one. Data
        Status shows which accounts and months are still missing.
      </p>
    </section>
  );
}

export function UploadResults({ results }: { results: UploadResult[] }) {
  const saved = results.filter((r) => r.outcome === "stored").length;
  return (
    <div className="mt-4 rounded-2xl bg-ground px-4 py-3">
      <p className="font-semibold">
        {saved} of {results.length} saved.
      </p>
      <ul className="mt-2 space-y-2">
        {results.map((r, i) => (
          <li key={`${r.file_name}-${i}`} className="flex flex-wrap items-baseline gap-2">
            <span className={`pill ${OUTCOME[r.outcome].className}`}>{OUTCOME[r.outcome].label}</span>
            <span className="font-semibold">{r.file_name}</span>
            <span className="text-muted">{r.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
