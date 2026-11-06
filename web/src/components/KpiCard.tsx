/** A KPI tile (docs/design-system.md): label, big number, an optional note or change chip. */
export default function KpiCard({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "good" | "bad" | "attention";
}) {
  const box =
    tone === "attention" ? "border-transparent bg-attention-bg text-attention-ink" : "border-line bg-ground";
  const noteTone =
    tone === "good"
      ? "text-good-ink"
      : tone === "bad"
        ? "text-danger-ink"
        : tone === "attention"
          ? ""
          : "text-muted";
  return (
    <div className={`rounded-2xl border px-5 py-4 ${box}`}>
      <dt className="kpi-label" style={tone === "attention" ? { color: "inherit" } : undefined}>
        {label}
      </dt>
      <dd className={`num kpi-value ${tone === "bad" ? "text-danger-ink" : ""}`}>{value}</dd>
      {note && <dd className={`mt-1 text-sm ${noteTone}`}>{note}</dd>}
    </div>
  );
}
