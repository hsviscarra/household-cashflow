import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type DragEvent } from "react";
import { fetchStatements, uploadStatements, type UploadResult } from "../api";
import { StatementList } from "./import/StatementList";
import { BulkActions, UploadResults } from "./import/BulkActions";

export { backlog, type Standing, STANDING, standing, filterStatements } from "./import/shared";

const UPLOAD_CHUNK = 50;

export function StatementsCard() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const list = useQuery({ queryKey: ["statements"], queryFn: fetchStatements });
  const upload = useMutation({
    // The server takes 50 files per request: larger drops go in chunks, one after another.
    mutationFn: async (all: File[]) => {
      const out: UploadResult[] = [];
      for (let i = 0; i < all.length; i += UPLOAD_CHUNK)
        out.push(...(await uploadStatements(all.slice(i, i + UPLOAD_CHUNK))));
      return out;
    },
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
        Upload PDFs from Bank of America, Capital One, Banco Pichincha, Produbanco, Diners or Pacificard, one
        or many at a time. Each file is kept as it is; the same file is never saved twice. Read lines checks a
        statement against its own totals before anything is loaded.
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
              : "PDF only, up to 25 MB each; as many files as you like"}
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

      {list.data && <BulkActions statements={list.data} />}
      <StatementList statements={list.data} error={list.error as Error | null} />
    </div>
  );
}
