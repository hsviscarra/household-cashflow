import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchAlertSettings, saveAlertSettings } from "../api";

/** Which kinds of alert the daily email carries, and what it would say today (ADR-082). The Gmail
 * script sends it from your own Gmail when it checks in each morning; each alert is sent once. */
export default function AlertSettings() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["alerts"], queryFn: fetchAlertSettings });
  const save = useMutation({
    mutationFn: saveAlertSettings,
    onSuccess: (data) => qc.setQueryData(["alerts"], data),
  });
  const kinds = q.data?.kinds ?? [];
  if (!kinds.length) return null;
  const toggle = (key: string, on: boolean) =>
    save.mutate(kinds.filter((k) => (k.key === key ? !on : !k.on)).map((k) => k.key));
  const now = q.data?.now ?? [];
  return (
    <section aria-labelledby="alerts" className="card mt-6 p-5">
      <h2 id="alerts" className="font-display text-2xl font-bold">
        Email alerts
      </h2>
      <p className="mt-1 text-sm text-muted">
        Each morning the Gmail script emails you what needs you, each thing once. Untick what you don’t want
        to hear about.
      </p>
      <ul className="mt-3 space-y-2 text-sm">
        {kinds.map((k) => (
          <li key={k.key}>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={k.on}
                disabled={save.isPending}
                onChange={(e) => toggle(k.key, e.target.checked)}
              />
              {k.label}
            </label>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm text-muted">
        {now.length
          ? `Right now ${now.length} ${now.length === 1 ? "thing matches" : "things match"}:`
          : "Right now nothing matches."}
      </p>
      {now.length > 0 && (
        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
          {now.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      {save.error && <p className="mt-2 text-sm text-danger-ink">{(save.error as Error).message}</p>}
    </section>
  );
}
