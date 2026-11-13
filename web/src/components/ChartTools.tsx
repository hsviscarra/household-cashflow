import { askAbout } from "../ask";
import { downloadCsv, type CsvCell } from "../csv";

// What every chart offers beside it (ADR-094, ADR-101): its period when it has one, the numbers
// as a CSV file, and "Explain", which opens Ask Claude with a question about this chart.

export default function ChartTools<P extends string>({
  name,
  period,
  csv,
  explain,
}: {
  /** What the chart is called in the labels: "Cash flow". */
  name: string;
  period?: { value: P; options: Record<P, string>; onChange: (value: P) => void };
  /** The file's name and its rows, header first. */
  csv?: { file: string; rows: () => CsvCell[][] };
  /** The question written into Ask Claude. */
  explain?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {period && (
        <label className="flex items-center gap-2">
          <span className="text-muted">Period</span>
          <select
            className="field h-9 !w-36"
            aria-label={`${name}: period`}
            value={period.value}
            onChange={(e) => period.onChange(e.target.value as P)}
          >
            {(Object.keys(period.options) as P[]).map((k) => (
              <option key={k} value={k}>
                {period.options[k]}
              </option>
            ))}
          </select>
        </label>
      )}
      {csv && (
        <button
          type="button"
          className="btn btn-quiet h-9 px-3"
          aria-label={`${name}: download CSV`}
          onClick={() => downloadCsv(csv.file, csv.rows())}
        >
          Download CSV
        </button>
      )}
      {explain && (
        <button
          type="button"
          className="btn btn-quiet h-9 px-3"
          aria-label={`${name}: explain`}
          onClick={() => askAbout(explain)}
        >
          Explain
        </button>
      )}
    </div>
  );
}
