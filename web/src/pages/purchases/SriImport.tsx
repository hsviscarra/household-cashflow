import { type InvoiceUpload, findSriKeys, fetchSriInvoices } from "../../api";
import { useState } from "react";

export const SRI_BATCH = 10;

/** A text file's contents (FileReader works in every browser and in the tests). */
export function readText(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(new Error("The file couldn't be read."));
    r.readAsText(f);
  });
}

/** "Found 12 invoices: 5 new, 7 already here; 2 other documents skipped." */
export function sriFoundLine(k: { new: string[]; stored: number; other: number }): string {
  const n = k.new.length + k.stored;
  if (!n)
    return k.other ? `No invoices in it, only ${k.other} other documents.` : "No access keys found in it.";
  const other = k.other ? `; ${k.other} other ${k.other === 1 ? "document" : "documents"} skipped` : "";
  return `Found ${n} ${n === 1 ? "invoice" : "invoices"}: ${k.new.length} new, ${k.stored} already here${other}.`;
}

/** Invoices that never reached Gmail (ADR-037): the SRI's list of received documents, uploaded or
 * pasted; each new access key is fetched from the SRI in batches of ten. */
export function SriImport({
  onStatus,
  onResults,
}: {
  onStatus: (s: { message: string; tone: "good" | "bad" } | null) => void;
  onResults: (r: InvoiceUpload[]) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState("");
  const run = async (report: string) => {
    onStatus(null);
    try {
      setBusy("Reading the list…");
      const keys = await findSriKeys(report);
      const all: InvoiceUpload[] = [];
      for (let i = 0; i < keys.new.length; i += SRI_BATCH) {
        setBusy(`Getting ${Math.min(i + SRI_BATCH, keys.new.length)} of ${keys.new.length} from the SRI…`);
        all.push(...(await fetchSriInvoices(keys.new.slice(i, i + SRI_BATCH))));
      }
      const stored = all.filter((r) => r.outcome === "stored").length;
      onStatus({
        message: `${sriFoundLine(keys)}${keys.new.length ? ` Added ${stored}.` : ""}`,
        tone: stored === keys.new.length ? "good" : "bad",
      });
      onResults(all.filter((r) => r.outcome !== "stored" || all.length <= 20));
      setText("");
      setPasting(false);
    } catch (e) {
      onStatus({ message: (e as Error).message, tone: "bad" });
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <label className="btn btn-secondary cursor-pointer">
        {busy ?? "Upload the SRI list (.txt)"}
        <input
          type="file"
          accept=".txt,text/plain,.csv"
          className="sr-only"
          aria-label="SRI list of received documents"
          disabled={!!busy}
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void readText(f).then(run);
          }}
        />
      </label>
      <button
        type="button"
        className="btn btn-quiet"
        onClick={() => setPasting(!pasting)}
        aria-expanded={pasting}
      >
        Paste access keys
      </button>
      {pasting && (
        <form
          className="w-full"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) void run(text);
          }}
        >
          <label className="block">
            <span className="label">
              Access keys (49 digits each), or the whole list copied from SRI en línea
            </span>
            <textarea
              className="field h-28 py-2 font-mono text-sm"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary mt-2" disabled={!!busy || !text.trim()}>
            Get these invoices from the SRI
          </button>
        </form>
      )}
    </>
  );
}
