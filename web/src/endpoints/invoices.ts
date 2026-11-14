import { upload } from "./history";
import { ApiError, send } from "./settings";

// ---------- F22: Interactive Brokers ----------
export type Position = {
  symbol: string;
  description: string | null;
  asset_class: string;
  currency: string;
  quantity: string;
  price: string;
  value: string;
  cost_basis: string | null;
  unrealized: string | null;
};

export type Portfolio = {
  holding_id: number | null;
  as_of: string | null;
  total: string | null;
  cash: string | null;
  previous_total: string | null;
  previous_as_of: string | null;
  stale: boolean;
  positions: Position[];
};

export type PortfolioRead = {
  holding_id: number;
  as_of: string;
  total: string;
  cash: string;
  positions: number;
};

export const fetchPortfolio = () => send<Portfolio>("GET", "/api/investments/ibkr");

export const uploadFlex = (file: File) => upload<PortfolioRead>("/api/investments/ibkr/upload", file);

// ---------- F21: electronic invoices ----------
export type InvoiceLine = {
  line_no: number;
  description: string;
  product_key: string;
  quantity: string;
  unit_price: string;
  total: string;
  product_group: string | null;
  group_source: "rule" | "keyword" | "claude" | "confirmed" | null;
  category_id?: number | null; // the app category (ADR-050)
  category_path?: string | null;
};

export type Invoice = {
  invoice_id: number;
  issuer_name: string;
  number: string;
  issue_date: string;
  subtotal: string;
  tax: string;
  total: string;
  received_by: string;
  paid_with: { transaction_id: number; txn_date: string; account: string | null; description: string } | null;
  lines: InvoiceLine[];
};

export type Purchases = {
  month: string;
  total: string;
  matched_total: string;
  groups: { group: string; amount: string; lines: number }[];
  to_group: {
    product_key: string;
    description: string;
    lines: number;
    amount: string;
    suggested_group: string | null;
  }[];
  invoices: Invoice[];
  product_groups: string[];
  suggestions_available: boolean;
};

export type InvoiceUpload = {
  file_name: string;
  outcome: "stored" | "duplicate" | "skipped" | "rejected";
  message: string;
  invoice_id: number | null;
};

export const fetchPurchases = (month: string) =>
  send<Purchases>("GET", `/api/invoices?month=${encodeURIComponent(month)}`);

export const setProductGroup = (product_key: string, product_group: string) =>
  send<{ product_key: string; product_group: string; lines_updated: number }>(
    "PUT",
    "/api/invoices/products",
    {
      product_key,
      product_group,
    },
  );

export const setProductCategory = (product_key: string, category_id: number | null) =>
  send<{ product_key: string; category_id: number | null; lines_updated: number }>(
    "PUT",
    "/api/invoices/products",
    { product_key, category_id },
  );

export const suggestProductGroups = (month: string) =>
  send<{ products: number }>("POST", `/api/invoices/suggest?month=${encodeURIComponent(month)}`);

export async function uploadInvoices(files: File[]): Promise<InvoiceUpload[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const resp = await fetch("/api/invoices", {
    method: "POST",
    body: form,
    headers: { Accept: "application/json" },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(typeof detail === "string" ? detail : `Upload failed (${resp.status}).`, resp.status);
  }
  return data as InvoiceUpload[];
}

// ---------- people and transfer notes (ADR-023) ----------
export type Person = {
  counterparty_id: number;
  name: string;
  patterns: string | null;
  category_id: number | null;
  category_path: string | null;
  holding_id: number | null;
  holding_name: string | null;
  is_active: boolean;
  notes: string | null;
  lines: number;
  received: string;
  paid: string;
};

export type PersonInput = {
  name: string;
  patterns?: string | null;
  category_id?: number | null;
  holding_id?: number | null;
  notes?: string | null;
  new_balance?: boolean;
  opening_balance?: string | null;
  opening_as_of?: string | null;
};

export type PersonLine = {
  transaction_id: number;
  txn_date: string;
  amount: string;
  description: string;
  account_name: string | null;
  category_path: string | null;
  notes: string | null;
};

export type TransferNote = {
  note_id: number;
  txn_date: string;
  amount: string;
  account_id: number | null;
  account_name: string | null;
  counterparty_id: number | null;
  person: string | null;
  category_id: number | null;
  category_path: string | null;
  other_party: string | null;
  description: string | null;
  share: string | null;
  source: "manual" | "email";
  transaction_id: number | null;
  line_date: string | null;
  line_description: string | null;
  created_by: string;
};

export type NoteInput = {
  txn_date: string;
  direction: "sent" | "received";
  amount: string;
  account_id?: number | null;
  counterparty_id?: number | null;
  category_id?: number | null;
  other_party?: string | null;
  description?: string | null;
  share?: string | null;
};

export const fetchPeople = () => send<Person[]>("GET", "/api/people");

export const createPerson = (p: PersonInput) => send<Person>("POST", "/api/people", p);

export const updatePerson = (id: number, p: Partial<PersonInput> & { is_active?: boolean }) =>
  send<Person>("PATCH", `/api/people/${id}`, p);

export const deletePerson = (id: number) => send<void>("DELETE", `/api/people/${id}`);

export const fetchPersonLines = (id: number) => send<PersonLine[]>("GET", `/api/people/${id}/lines`);

export const fetchNotes = (state: "open" | "matched" | "all" = "all") =>
  send<TransferNote[]>("GET", `/api/transfer-notes?state=${state}`);

export const createNote = (n: NoteInput) => send<TransferNote>("POST", "/api/transfer-notes", n);

export const deleteNote = (id: number) => send<void>("DELETE", `/api/transfer-notes/${id}`);

export const matchNotes = () =>
  send<{ matched: number; tagged: number }>("POST", "/api/transfer-notes/match");
