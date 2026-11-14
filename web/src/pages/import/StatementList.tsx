import { type Statement, statementFileUrl, fetchAccounts, assignStatement, readStatement } from "../../api";
import { useState } from "react";
import { type Standing, standing, filterStatements, NO_ACCOUNT, STANDING, shortDate, STATUS } from "./shared";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";

export function StatementList({
  statements,
  error,
}: {
  statements: Statement[] | undefined;
  error: Error | null;
}) {
  const [account, setAccount] = useState("");
  const [only, setOnly] = useState<Standing | "">("");
  const [text, setText] = useState("");
  if (error)
    return (
      <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
        Could not load the statements: {error.message}
      </p>
    );
  if (!statements) return <p className="mt-6 text-muted">Loading statements…</p>;
  if (!statements.length) return <p className="mt-6 text-muted">No statements uploaded yet.</p>;

  const accounts = new Map<string, string>();
  statements.forEach((s) => s.accounts.forEach((a) => accounts.set(String(a.account_id), a.name)));
  const counts = new Map<Standing, number>();
  statements.forEach((s) => counts.set(standing(s), (counts.get(standing(s)) ?? 0) + 1));
  const shown = filterStatements(statements, { account, standing: only, text });
  const filtered = account !== "" || only !== "" || text.trim() !== "";

  return (
    <>
      <div className="mt-6 flex flex-wrap items-end gap-3" role="search" aria-label="Filter statements">
        <label className="min-w-48 flex-1 md:max-w-xs">
          <span className="label">Account</span>
          <select className="field" value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">All accounts</option>
            {[...accounts.entries()]
              .sort(([, a], [, b]) => a.localeCompare(b))
              .map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            {statements.some((s) => !s.accounts.length) && <option value={NO_ACCOUNT}>No account yet</option>}
          </select>
        </label>
        <label className="min-w-48 flex-1 md:max-w-xs">
          <span className="label">Status</span>
          <select className="field" value={only} onChange={(e) => setOnly(e.target.value as Standing | "")}>
            <option value="">Any status</option>
            {(Object.keys(STANDING) as Standing[]).map((k) => (
              <option key={k} value={k}>
                {STANDING[k]} ({counts.get(k) ?? 0})
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-48 flex-1 md:max-w-xs">
          <span className="label">File name</span>
          <input
            className="field"
            type="search"
            placeholder="e.g. 202610 or Diners"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        {filtered && (
          <button
            className="btn btn-quiet"
            onClick={() => {
              setAccount("");
              setOnly("");
              setText("");
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      <p className="mt-2 text-sm text-muted" aria-live="polite">
        {filtered
          ? `Showing ${shown.length} of ${statements.length} statements.`
          : `${statements.length} statements.`}
      </p>
      {shown.length === 0 ? (
        <p className="mt-4 text-muted">No statement matches these filters.</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-2xl border border-line bg-ground">
          <table className="w-full text-sm">
            <caption className="sr-only">Uploaded statements</caption>
            <thead className="text-muted max-md:sr-only">
              <tr>
                <th scope="col" className="px-4 py-3 text-left font-semibold">
                  File
                </th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">
                  Account
                </th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">
                  Period
                </th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">
                  Uploaded
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shown.map((s) => (
                // On a phone each row stacks into a small card.
                <tr
                  key={s.statement_file_id}
                  className="max-md:flex max-md:flex-col max-md:gap-1 max-md:py-3"
                >
                  <td className="px-4 py-2 align-top max-md:py-0">
                    <a
                      href={statementFileUrl(s.statement_file_id)}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-primary underline-offset-2 hover:underline"
                    >
                      {s.file_name}
                    </a>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-muted">
                      {s.source !== "unknown" && <span>{s.source_label}</span>}
                      <StatementAction statement={s} />
                    </div>
                  </td>
                  <td className="px-4 py-2 align-top max-md:py-0">
                    {s.status === "needs_account" ? (
                      <AccountPicker statement={s} />
                    ) : (
                      <>
                        {s.accounts.map((a) => (
                          <div key={a.account_id}>
                            {a.name}
                            {a.last4 && <span className="num text-muted"> •••• {a.last4}</span>}
                          </div>
                        ))}
                        {s.account_match === "by_bank" && (
                          <div className="text-muted">
                            Matched by bank
                            {s.last4_found.length ? ` (file shows •••• ${s.last4_found.join(", ")})` : ""}
                          </div>
                        )}
                        {s.account_match === "owner" && (
                          <div className="text-muted">Matched by the cardholder’s name</div>
                        )}
                      </>
                    )}
                  </td>
                  <td className="num px-4 py-2 align-top max-md:py-0">
                    {s.period_start && s.period_end ? (
                      `${shortDate(s.period_start)} – ${shortDate(s.period_end)}`
                    ) : (
                      <span className="text-muted">Period not read yet</span>
                    )}
                  </td>
                  <td className="px-4 py-2 align-top text-muted max-md:py-0">
                    {s.page_count} page{s.page_count === 1 ? "" : "s"} ·{" "}
                    {new Date(s.uploaded_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}{" "}
                    · {s.uploaded_by}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function AccountPicker({ statement }: { statement: Statement }) {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const [choice, setChoice] = useState("");
  const save = useMutation({
    mutationFn: (id: number) => assignStatement(statement.statement_file_id, [id]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["statements"] }),
  });
  const options = (accounts.data ?? []).filter(
    (a) =>
      a.is_active && a.institution.toLowerCase().includes(statement.source_label.split(" ")[0].toLowerCase()),
  );
  const all = options.length ? options : (accounts.data ?? []).filter((a) => a.is_active);

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (choice) save.mutate(Number(choice));
      }}
    >
      <label>
        <span className="sr-only">Account for {statement.file_name}</span>
        <select className="field h-9 py-0" value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">Choose account</option>
          {all.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="btn btn-secondary h-9 px-4" disabled={!choice || save.isPending}>
        Save
      </button>
      {save.error && <span className="text-danger-ink">{(save.error as Error).message}</span>}
    </form>
  );
}

export function StatementAction({ statement: s }: { statement: Statement }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const read = useMutation({
    mutationFn: () => readStatement(s.statement_file_id),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["statements"] });
      navigate(`/import/batches/${b.batch_id}`);
    },
  });

  if (s.status !== "detected")
    return <span className={`pill ${STATUS[s.status].className}`}>{STATUS[s.status].label}</span>;
  if (s.batch?.status === "approved")
    return (
      <>
        <span className="pill pill-good">Loaded</span>
        <Link
          to={`/import/batches/${s.batch.batch_id}`}
          className="text-primary underline-offset-2 hover:underline"
        >
          View
        </Link>
      </>
    );
  if (s.batch?.status === "preview")
    return (
      <>
        <span className="pill bg-attention-bg text-attention-ink">Waiting for approval</span>
        <Link
          to={`/import/batches/${s.batch.batch_id}`}
          className="text-primary underline-offset-2 hover:underline"
        >
          Review
        </Link>
      </>
    );
  if (!s.can_read) return <span className="pill pill-muted">Uploaded</span>;
  return (
    <>
      <button
        className="btn btn-secondary h-9 px-4"
        disabled={read.isPending}
        onClick={() => read.mutate()}
        aria-label={`Read lines of ${s.file_name}`}
      >
        {read.isPending ? "Reading…" : "Read lines"}
      </button>
      {read.isPending && s.source === "pacificard" && (
        <span className="text-muted" role="status">
          This statement is a picture, so it’s read with OCR; it takes up to a minute.
        </span>
      )}
      {read.error && <span className="text-danger-ink">{(read.error as Error).message}</span>}
    </>
  );
}
