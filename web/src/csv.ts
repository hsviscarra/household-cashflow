// CSV for "Download CSV" everywhere: one way to quote a cell and one way to hand the file over.

export type CsvCell = string | number;

const quoted = (v: CsvCell) => {
  const text = String(v);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

/** Rows as CSV text; cells with a comma, a quote or a line break are quoted. */
export const csvOf = (rows: CsvCell[][]) => rows.map((r) => r.map(quoted).join(",")).join("\n");

/** Hand a text file to the browser to save. */
export function downloadText(name: string, text: string, type = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const downloadCsv = (name: string, rows: CsvCell[][]) => downloadText(name, csvOf(rows));
