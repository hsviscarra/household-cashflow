import { exportUrl } from "../api";

/** "Export: CSV · Excel" for one dataset, for a month (YYYY-MM) or a year. */
export function ExportLinks({
  dataset,
  label,
  month,
  year,
}: {
  dataset: string;
  label: string;
  month?: string;
  year?: number;
}) {
  const period = { month, year };
  return (
    <p className="text-sm text-muted">
      Export {label}:{" "}
      <a className="text-primary underline" href={exportUrl(dataset, "csv", period)} download>
        CSV
      </a>{" "}
      ·{" "}
      <a className="text-primary underline" href={exportUrl(dataset, "xlsx", period)} download>
        Excel
      </a>
    </p>
  );
}
