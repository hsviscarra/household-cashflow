import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";

import {
  assignStatement,
  fetchAccounts,
  fetchStatements,
  statementFileUrl,
  uploadStatements,
  type Statement,
  type UploadResult,
} from "../api";

const OUTCOME = {
  stored: { label: "Saved", className: "pill-good" },
  duplicate: { label: "Already uploaded", className: "pill-muted" },
  rejected: { label: "Not saved", className: "pill-bad" },
} as const;

const STATUS = {
  detected: { label: "Ready", className: "pill-good" },
  needs_account: { label: "Choose account", className: "bg-attention-bg text-attention-ink" },
  unknown_format: { label: "Unknown format", className: "bg-attention-bg text-attention-ink" },
} as const;

const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export function StatementsCard() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const list = useQuery({ queryKey: ["statements"], queryFn: fetchStatements });
  const upload = useMutation({
    mutationFn: uploadStatements,
    onSuccess: () => {
      setFiles([]);
      qc.invalidateQueries({ queryKey: ["statements"] });
    },
  });

  const pick = (picked: FileList | null) => {
    upload.reset();
    setFiles(picked ? Array.from(picked) : []);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files);
  };

  return (
    <div className="mt-8 rounded-2xl bg-surface p-4 md:p-6">
      <h2 className="font-display text-2xl font-bold">Statements</h2>
      <p className="mt-1 text-muted">
        Upload PDFs from Bank of America, Capital One, Banco Pichincha, Produbanco or Diners, one or many at a
        time. Each file is kept as it is; the same file is never saved twice. Reading the lines comes with the
        next features.
      </p>

      <form
        className="mt-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (files.length) upload.mutate(files);
        }}
      >
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center ${
            dragging ? "border-primary bg-info-bg" : "border-line bg-ground"
          }`}
        >
          <span className="font-semibold">Drop statement PDFs here or choose files</span>
          <span className="text-sm text-muted">
            {files.length
              ? `${files.length} file${files.length === 1 ? "" : "s"} chosen: ${files.map((f) => f.name).join(", ")}`
              : "PDF only, up to 25 MB each, 50 files at a time"}
          </span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="sr-only"
            aria-label="Statement PDFs"
            onChange={(e) => pick(e.target.files)}
          />
        </label>
        <button type="submit" className="btn btn-primary mt-3" disabled={!files.length || upload.isPending}>
          {upload.isPending ? "Uploading…" : "Upload statements"}
        </button>
      </form>

      <div aria-live="polite">
        {upload.error && (
          <p className="mt-4 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
            {(upload.error as Error).message}
          </p>
        )}
        {upload.data && <UploadResults results={upload.data} />}
      </div>

      <StatementList statements={list.data} error={list.error as Error | null} />
    </div>
  );
}

function UploadResults({ results }: { results: UploadResult[] }) {
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

function StatementList({ statements, error }: { statements: Statement[] | undefined; error: Error | null }) {
  if (error)
    return (
      <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
        Could not load the statements: {error.message}
      </p>
    );
  if (!statements) return <p className="mt-6 text-muted">Loading statements…</p>;
  if (!statements.length) return <p className="mt-6 text-muted">No statements uploaded yet.</p>;

  return (
    <div className="mt-6 overflow-x-auto rounded-2xl border border-line bg-ground">
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
          {statements.map((s) => (
            // On a phone each row stacks into a small card.
            <tr key={s.statement_file_id} className="max-md:flex max-md:flex-col max-md:gap-1 max-md:py-3">
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
                  <span className={`pill ${STATUS[s.status].className}`}>{STATUS[s.status].label}</span>
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
                {new Date(s.uploaded_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })} ·{" "}
                {s.uploaded_by}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccountPicker({ statement }: { statement: Statement }) {
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
