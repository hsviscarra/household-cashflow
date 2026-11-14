import { type Notify } from "./shared";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { fetchBankSync, type BankSync, runBankSync, linkBankSync } from "../../api";
import { money } from "../../money";

/** SimpleFIN accounts and the app account each one feeds (ADR-044). */
export function BankSyncTab({ notify }: { notify: Notify }) {
  const qc = useQueryClient();
  const sync = useQuery({ queryKey: ["bank-sync"], queryFn: fetchBankSync });
  const done = (b: BankSync) => {
    qc.setQueryData(["bank-sync"], b);
    ["transactions", "review", "cashflow", "spending", "home"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    );
  };
  const run = useMutation({
    mutationFn: () => runBankSync(false),
    onSuccess: (b) => {
      done(b);
      notify(`Synced: ${b.added ?? 0} new ${b.added === 1 ? "line" : "lines"}.`);
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const link = useMutation({
    mutationFn: linkBankSync,
    onSuccess: (b) => {
      done(b);
      notify("Saved. The next sync brings that account's movements.");
    },
    onError: (e: Error) => notify(e.message, "bad"),
  });
  const b = sync.data;
  if (sync.error)
    return (
      <section role="alert" className="card space-y-3 p-5">
        <h2 className="text-lg font-semibold">Bank sync didn’t load</h2>
        <p className="text-sm text-muted">{(sync.error as Error).message}</p>
        <button className="btn btn-secondary" onClick={() => void sync.refetch()}>
          Try again
        </button>
      </section>
    );
  if (!b) return <p className="text-muted">Loading…</p>;
  if (!b.configured)
    return (
      <section className="card space-y-2 p-5">
        <h2 className="text-lg font-semibold">Bank sync is not set up</h2>
        <p className="text-sm text-muted">
          Connect your banks on SimpleFIN Bridge, make a setup token and run{" "}
          <code className="font-mono">./infra/azure/setup-simplefin.sh</code>.
        </p>
      </section>
    );
  const last = b.last_run;
  return (
    <div className="space-y-4">
      <section className="card flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <h2 className="text-lg font-semibold">Bank sync</h2>
          <p className="text-sm text-muted">
            {last ? `Last synced ${new Date(last.at + "Z").toLocaleString()}` : "Not synced yet"} ·{" "}
            {b.pending_lines} synced {b.pending_lines === 1 ? "line waits" : "lines wait"} for a statement. It
            syncs by itself when you open the app, twice a day at most.
          </p>
        </div>
        <button className="btn btn-primary" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Syncing…" : "Sync now"}
        </button>
      </section>
      {last?.errors.map((e) => (
        <p key={e} role="alert" className="card border-warn p-4 text-sm text-warn">
          SimpleFIN: {e}
        </p>
      ))}
      {last && (
        <section aria-label="Accounts SimpleFIN reaches" className="card overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line">
                <th className="px-4 py-2 text-sm font-semibold text-muted">Bank account</th>
                <th className="px-4 py-2 text-right text-sm font-semibold text-muted">Balance</th>
                <th className="px-4 py-2 text-sm font-semibold text-muted">Feeds this account</th>
              </tr>
            </thead>
            <tbody>
              {last.accounts.map((a) => {
                const mine = b.accounts.find((x) => x.sync_id === a.sync_id);
                return (
                  <tr key={a.sync_id} className="border-b border-line last:border-0">
                    <td className="px-4 py-2">
                      <span className="font-semibold">{a.org}</span> · {a.name}
                      <span className="block text-sm text-muted">
                        {a.movements} movements in the last 44 days
                      </span>
                    </td>
                    <td className="num px-4 py-2 text-right">{a.balance ? money(a.balance) : "—"}</td>
                    <td className="px-4 py-2">
                      <select
                        className="field"
                        aria-label={`App account for ${a.org} ${a.name}`}
                        value={mine?.account_id ?? ""}
                        disabled={link.isPending}
                        onChange={(e) =>
                          link.mutate({
                            sync_id: a.sync_id,
                            account_id: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                      >
                        <option value="">Not linked</option>
                        {b.accounts.map((x) => (
                          <option key={x.account_id} value={x.account_id}>
                            {x.institution} · {x.name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
      <p className="text-sm text-muted">
        Synced lines are pending until the month’s statement is approved; then each statement line takes its
        place and keeps the category, person and notes you gave it.
      </p>
    </div>
  );
}
