import { type Txn } from "../../api";
import { type Column } from "../../components/DataTable";
import { monthLong, num, showAmount } from "../../money";
import { CategoryCell, EditToggle, NoteCell } from "./Cells";
import { counted, day, SOURCE_LABEL } from "./shared";

/** The shared table's columns (ADR-091): the description first, the amount and Edit last, the
 * rest chosen. `show` says which columns are on: the note shows under the description while its
 * own column is hidden. */
export function txnColumns(
  show: (column: string) => boolean,
  names: Map<number, string>,
  open: number | null,
  setOpen: (id: number | null) => void,
): Column<Txn>[] {
  const account = (t: Txn) => t.account_name ?? SOURCE_LABEL[t.source] ?? t.source;
  return [
    {
      id: "description",
      label: "Description",
      fixed: true,
      sort: (t) => t.description,
      cell: (t) => (
        <span className={t.parent_transaction_id ? "block pl-4" : ""}>
          {t.parent_transaction_id && <span aria-hidden>↳ </span>}
          <span className={t.parts ? "line-through" : ""}>{t.description}</span>
          {!show("note") && t.notes && <span className="block text-xs text-muted">{t.notes}</span>}
        </span>
      ),
    },
    {
      id: "date",
      label: "Date",
      sort: (t) => t.txn_date,
      group: (t) => monthLong(`${t.txn_date.slice(0, 7)}-01`),
      cell: (t) => <span className="num whitespace-nowrap">{day(t.txn_date)}</span>,
    },
    {
      id: "account",
      label: "Account",
      sort: account,
      group: account,
      cell: (t) => <span className="text-muted">{account(t)}</span>,
    },
    {
      id: "who",
      label: "Who",
      sort: (t) => t.person ?? "",
      group: (t) => t.person ?? "Nobody",
      cell: (t) => t.person,
    },
    {
      id: "category",
      label: "Category",
      sort: (t) => t.category_path ?? "",
      group: (t) => t.category_path ?? "No category yet",
      cell: (t) => <CategoryCell t={t} />,
    },
    { id: "note", label: "Note / person", cell: (t) => <NoteCell t={t} names={names} /> },
    {
      id: "merchant",
      label: "Merchant (cleaned)",
      sort: (t) => t.merchant ?? "",
      group: (t) => t.merchant ?? "No merchant",
      cell: (t) => <span className="text-muted">{t.merchant}</span>,
    },
    {
      id: "post",
      label: "Posted date",
      sort: (t) => t.post_date ?? "",
      cell: (t) => <span className="num whitespace-nowrap">{t.post_date ? day(t.post_date) : ""}</span>,
    },
    {
      id: "month",
      label: "Counts in",
      sort: (t) => t.cash_month,
      group: (t) => monthLong(t.cash_month),
      cell: (t) => <span className="whitespace-nowrap">{monthLong(t.cash_month)}</span>,
    },
    {
      id: "country",
      label: "Country",
      sort: (t) => t.country ?? "",
      group: (t) => t.country ?? "No country",
      cell: (t) => <span className="text-muted">{t.country}</span>,
    },
    {
      id: "amount",
      label: "Amount",
      fixed: "end",
      align: "right",
      sort: (t) => num(t.amount),
      total: (t) => (counted(t) ? num(t.amount) : 0), // a split line's parts count, not the line
      cell: (t) => <span className={t.parts ? "line-through" : ""}>{showAmount(t.amount)}</span>,
    },
    {
      id: "edit",
      label: "Edit",
      fixed: "end",
      align: "right",
      header: <span className="sr-only">Edit</span>,
      cell: (t) => <EditToggle t={t} open={open} setOpen={setOpen} />,
    },
  ];
}
