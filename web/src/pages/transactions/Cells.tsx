import { type Txn, unlinkTransfer } from "../../api";
import { num, money, showAmount } from "../../money";
import { Link, useLocation } from "react-router-dom";
import { useSavedViews, usePerson, type Person } from "../../prefs";
import { HOW, day, useInvalidate } from "./shared";
import { useMutation } from "@tanstack/react-query";

/** What the ticked lines add up to: money out, money in and the net; transfers left out. */
export function TickedTotals({ lines }: { lines: Txn[] }) {
  const flows = lines.filter((t) => t.type !== "transfer");
  const out = flows.filter((t) => num(t.amount) < 0).reduce((s, t) => s - num(t.amount), 0);
  const into = flows.filter((t) => num(t.amount) > 0).reduce((s, t) => s + num(t.amount), 0);
  return (
    <>
      <span>
        Out <span className="num font-semibold">{money(out)}</span>
      </span>
      <span>
        In <span className="num font-semibold">{money(into)}</span>
      </span>
      <span>
        Net <span className="num font-semibold">{showAmount(into - out)}</span>
      </span>
    </>
  );
}

export function NoteCell({ t, names }: { t: Txn; names: Map<number, string> }) {
  const who = t.counterparty_id ? names.get(t.counterparty_id) : null;
  if (!who && !t.notes) return null;
  return (
    <span className="block text-sm">
      {who && (
        <Link to={`/transactions?cp=${t.counterparty_id}&months=12`} className="pill pill-muted mr-1">
          {who}
        </Link>
      )}
      {t.notes && <span className="text-muted">{t.notes}</span>}
    </span>
  );
}

/** Saved views of this page as tabs (ADR-030): "All" and each view saved here. */
export function ViewTabs({ month }: { month: string }) {
  const { views } = useSavedViews();
  const [, setPerson] = usePerson();
  const { search } = useLocation();
  const mine = views.filter((v) => v.path === "/transactions");
  const strip = (q: string) => {
    const p = new URLSearchParams(q);
    p.delete("month");
    p.sort();
    return p.toString();
  };
  const here = strip(search);
  return (
    <nav aria-label="Saved views" className="mt-6 flex flex-wrap gap-1 border-b border-line">
      {[{ id: "all", name: "All", search: "", person: null as Person | null }, ...mine].map((v) => {
        const on = strip(v.search) === here;
        const q = new URLSearchParams(v.search);
        if (!q.has("month")) q.set("month", month);
        return (
          <Link
            key={v.id}
            to={`/transactions?${q.toString()}`}
            aria-current={on ? "page" : undefined}
            onClick={() => v.person && setPerson(v.person)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${on ? "border-primary text-ink" : "border-transparent text-muted hover:text-ink"}`}
          >
            {v.name}
          </Link>
        );
      })}
    </nav>
  );
}

export function CategoryCell({ t }: { t: Txn }) {
  if (t.parts) return <span className="pill pill-muted">Split into {t.parts}</span>;
  if (!t.category_path)
    return <span className="pill bg-attention-bg text-attention-ink">Needs a category</span>;
  return (
    <span>
      {t.category_path}
      {t.category_source && t.category_source !== "split" && t.category_source !== "match" && (
        <span className="text-xs text-muted"> · {HOW[t.category_source] ?? t.category_source}</span>
      )}
      {t.transfer_with && (
        <span className="block text-xs text-muted">
          ↔ {t.transfer_with.account_name ?? "another account"}, {day(t.transfer_with.txn_date)}
        </span>
      )}
    </span>
  );
}

export function UnlinkTransfer({ t }: { t: Txn }) {
  const invalidate = useInvalidate();
  const unlink = useMutation({
    mutationFn: () => unlinkTransfer(t.transfer_group_id!),
    onSuccess: invalidate,
  });
  if (!t.transfer_group_id || !t.transfer_with) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-info-bg px-4 py-3 text-sm">
      <span>
        Matched transfer: the other side is <strong>{t.transfer_with.description}</strong> on{" "}
        {t.transfer_with.account_name ?? "another account"}, {day(t.transfer_with.txn_date)} (
        <span className="num">{showAmount(t.transfer_with.amount)}</span>).
      </span>
      <button
        type="button"
        className="btn btn-quiet h-9 px-3"
        disabled={unlink.isPending}
        onClick={() => unlink.mutate()}
      >
        Not the same money: unlink
      </button>
      {unlink.error && <span className="text-danger-ink">{(unlink.error as Error).message}</span>}
    </div>
  );
}

export function EditToggle({
  t,
  open,
  setOpen,
}: {
  t: Txn;
  open: number | null;
  setOpen: (id: number | null) => void;
}) {
  const isOpen = open === t.transaction_id;
  return (
    <button
      className="btn btn-quiet h-9 px-3 text-sm"
      aria-expanded={isOpen}
      aria-label={`${isOpen ? "Close" : "Edit"} ${t.description} on ${day(t.txn_date)}`}
      onClick={() => setOpen(isOpen ? null : t.transaction_id)}
    >
      {isOpen ? "Close" : "Edit"}
    </button>
  );
}
