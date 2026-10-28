import { useQuery } from "@tanstack/react-query";

import { fetchBackups, type BackupStatus } from "../api";

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
const size = (bytes: number) =>
  bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;

/** "Last backup Oct 28, 2026, 3:18 AM · 2.1 MB · 18,240 rows" or why it needs attention. */
export function backupLine(s: BackupStatus): string {
  if (!s.backup) return s.where === "azure" ? "No backup yet." : "Backups run in Azure; none here.";
  const b = s.backup;
  return `Last backup ${when(b.finished_at)} · ${size(b.size)} · ${b.rows.toLocaleString("en-US")} rows`;
}

export function drillLine(s: BackupStatus): string {
  if (!s.drill) return "No restore drill yet.";
  const d = s.drill;
  return d.ok
    ? `Last restore drill ${when(d.finished_at)}: restored and matched every table.`
    : `Last restore drill ${when(d.finished_at)} failed: ${(d.problems ?? []).slice(0, 2).join(" ")}`;
}

export function BackupPanel() {
  const q = useQuery({ queryKey: ["backups"], queryFn: fetchBackups });
  const s = q.data;
  if (q.error) return null; // the months above matter more; the panel just stays away
  if (!s) return null;
  const local = s.where === "local" && !s.backup;
  const attention = !local && (s.backup_overdue || s.drill_overdue || s.error);
  return (
    <section
      aria-label="Backups"
      className={`mt-8 rounded-2xl px-4 py-3 ${
        local ? "bg-info-bg" : attention ? "bg-attention-bg text-attention-ink" : "bg-good-bg text-good-ink"
      }`}
    >
      <h2 className="font-display text-xl font-bold">Backups</h2>
      {s.error ? (
        <p className="mt-1 text-sm">{s.error}</p>
      ) : (
        <>
          <p className="mt-1 text-sm">
            {backupLine(s)}
            {!local && s.backup_overdue && " · more than a day and a half ago: check the backup job."}
          </p>
          {!local && (
            <p className="text-sm">
              {drillLine(s)}
              {s.drill?.ok && s.drill_overdue && " More than 40 days ago."}
            </p>
          )}
          <p className="mt-1 text-xs opacity-80">
            Nightly copies of the database are kept 30 days; once a month one is restored to a scratch
            database and checked.
          </p>
        </>
      )}
    </section>
  );
}
