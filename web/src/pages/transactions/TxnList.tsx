import { type Txn } from "../../api";
import { showAmount } from "../../money";
import { CategoryCell, EditToggle, NoteCell } from "./Cells";
import { day, SOURCE_LABEL } from "./shared";
import { TxnEditor } from "./TxnEditor";

/** The lines as a list on a phone, where the table doesn't fit; the line open for editing
 * shows its editor under it. */
export function TxnList({
  rows,
  names,
  open,
  setOpen,
}: {
  rows: Txn[];
  names: Map<number, string>;
  open: number | null;
  setOpen: (id: number | null) => void;
}) {
  return (
    <>
      {rows.map((t) => (
        <li key={t.transaction_id} className={`px-4 py-3 ${t.parent_transaction_id ? "pl-8" : ""}`}>
          <div className="flex items-baseline justify-between gap-3">
            <span className={`font-semibold ${t.parts ? "text-muted line-through" : ""}`}>
              {t.parent_transaction_id && <span aria-hidden>↳ </span>}
              {t.description}
            </span>
            <span className={`num shrink-0 ${t.parts ? "text-muted line-through" : ""}`}>
              {showAmount(t.amount)}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted">
            <span className="num">{day(t.txn_date)}</span>
            <span>· {t.account_name ?? SOURCE_LABEL[t.source] ?? t.source}</span>
            {t.person && <span>· {t.person}</span>}
            <span>·</span>
            <CategoryCell t={t} />
          </div>
          <NoteCell t={t} names={names} />
          <EditToggle t={t} open={open} setOpen={setOpen} />
          {open === t.transaction_id && (
            <div className="mt-3">
              <TxnEditor t={t} onDone={() => setOpen(null)} />
            </div>
          )}
        </li>
      ))}
    </>
  );
}
