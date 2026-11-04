import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Statement } from "../api";
import { filterStatements, standing, StatementsCard } from "./ImportStatements";

const base: Statement = {
  statement_file_id: 1,
  file_name: "eStmt.pdf",
  source: "bofa",
  source_label: "Bank of America",
  status: "detected",
  accounts: [
    { account_id: 1, name: "BofA Adv Plus Banking", last4: "8872" },
    { account_id: 2, name: "BofA Regular Savings", last4: "1862" },
  ],
  account_match: "last4",
  last4_found: ["8872", "1862"],
  period_start: "2026-08-22",
  period_end: "2026-09-22",
  page_count: 6,
  size_bytes: 1000,
  uploaded_by: "hernan@example.com",
  uploaded_at: "2026-10-20T15:00:00",
  can_read: false,
  batch: null,
};
const DINERS: Statement = {
  ...base,
  statement_file_id: 2,
  file_name: "diners.pdf",
  source: "diners",
  source_label: "Diners Club",
  status: "needs_account",
  accounts: [],
  account_match: null,
  last4_found: ["1234"],
  period_start: null,
  period_end: null,
};
const ACCOUNTS = [
  {
    account_id: 7,
    name: "Diners Club Hernan",
    institution: "Diners Club",
    kind: "credit_card",
    owner: "Hernan",
    country: "EC",
    last4: null,
    is_active: true,
  },
  {
    account_id: 8,
    name: "Diners Club Lauren",
    institution: "Diners Club",
    kind: "credit_card",
    owner: "Lauren",
    country: "EC",
    last4: null,
    is_active: true,
  },
  {
    account_id: 1,
    name: "BofA Adv Plus Banking",
    institution: "Bank of America",
    kind: "checking",
    owner: "Joint",
    country: "US",
    last4: "8872",
    is_active: true,
  },
];

let listed: Statement[];
let calls: { method: string; url: string; body?: unknown }[];

beforeEach(() => {
  listed = [];
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body });
      if (url === "/api/statements" && method === "GET")
        return Promise.resolve(new Response(JSON.stringify(listed)));
      if (url === "/api/accounts") return Promise.resolve(new Response(JSON.stringify(ACCOUNTS)));
      if (url === "/api/statements" && method === "POST") {
        listed = [base, DINERS];
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                file_name: "eStmt.pdf",
                outcome: "stored",
                message: "Bank of America: BofA Adv Plus Banking.",
                statement: base,
              },
              {
                file_name: "diners.pdf",
                outcome: "stored",
                message: "Diners Club, but which account?",
                statement: DINERS,
              },
              {
                file_name: "old.pdf",
                outcome: "duplicate",
                message: "Already uploaded as eStmt.pdf on 2026-10-01.",
                statement: base,
              },
              {
                file_name: "locked.pdf",
                outcome: "rejected",
                message: "This PDF is password-protected.",
                statement: null,
              },
            ]),
          ),
        );
      }
      if (url === "/api/statements/2" && method === "PATCH") {
        listed = [
          base,
          {
            ...DINERS,
            status: "detected",
            account_match: "manual",
            accounts: [{ account_id: 8, name: "Diners Club Lauren", last4: null }],
          },
        ];
        return Promise.resolve(new Response(JSON.stringify(listed[1])));
      }
      if (url.endsWith("/read")) return new Promise<Response>(() => {}); // still reading
      return Promise.resolve(new Response("{}", { status: 404 }));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StatementsCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Import: statements", () => {
  it("uploads several files and reports each outcome", async () => {
    renderCard();
    expect(await screen.findByText("No statements uploaded yet.")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Upload statements" });
    expect(button).toBeDisabled();

    const files = ["eStmt.pdf", "diners.pdf", "old.pdf", "locked.pdf"].map(
      (n) => new File(["%PDF-"], n, { type: "application/pdf" }),
    );
    fireEvent.change(screen.getByLabelText("Statement PDFs"), { target: { files } });
    expect(screen.getByText(/4 files chosen/)).toBeInTheDocument();
    fireEvent.click(button);

    expect(await screen.findByText("2 of 4 saved.")).toBeInTheDocument();
    expect(screen.getByText("Already uploaded")).toBeInTheDocument();
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!;
    expect((post.body as FormData).getAll("files")).toHaveLength(4);

    const table = await screen.findByRole("table", { name: "Uploaded statements" });
    const row = within(table).getByRole("link", { name: "eStmt.pdf" }).closest("tr")!;
    expect(row).toHaveTextContent("BofA Regular Savings •••• 1862");
    expect(row).toHaveTextContent("Aug 22, 2026 – Sep 22, 2026");
    expect(within(table).getByRole("link", { name: "eStmt.pdf" })).toHaveAttribute(
      "href",
      "/api/statements/1/file",
    );
  });

  it("lets Hernan choose the account when the bank has several", async () => {
    listed = [DINERS];
    renderCard();
    const select = await screen.findByLabelText("Account for diners.pdf");
    await screen.findByRole("option", { name: "Diners Club Lauren" });
    expect(within(select).queryByRole("option", { name: "BofA Adv Plus Banking" })).toBeNull();
    fireEvent.change(select, { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Diners Club Lauren", { selector: "div" })).toBeInTheDocument();
    expect(screen.getAllByText("Uploaded", { selector: "span" })).toHaveLength(2);
    expect(calls.find((c) => c.method === "PATCH")?.body).toBe(JSON.stringify({ account_ids: [8] }));
  });

  it("says when the account was matched by the cardholder's name", async () => {
    listed = [
      {
        ...DINERS,
        status: "detected",
        accounts: [{ account_id: 7, name: "Diners Club Hernan", last4: null }],
        account_match: "owner",
      },
    ];
    renderCard();
    expect(await screen.findByText("Matched by the cardholder’s name")).toBeInTheDocument();
  });

  it("explains the wait while a picture statement is read with OCR", async () => {
    listed = [
      {
        ...base,
        statement_file_id: 3,
        file_name: "pacificard.pdf",
        source: "pacificard",
        source_label: "Pacificard (Banco del Pacífico)",
        accounts: [{ account_id: 9, name: "Pacificard Mastercard Black", last4: null }],
        can_read: true,
      },
    ];
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "Read lines of pacificard.pdf" }));
    expect(await screen.findByRole("status")).toHaveTextContent("read with OCR");
  });

  it("accepts dropped files", async () => {
    renderCard();
    await screen.findByText("No statements uploaded yet.");
    const zone = screen.getByText("Drop statement PDFs here or choose files").closest("label")!;
    fireEvent.dragOver(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "a.pdf")] } });
    expect(screen.getByText(/1 file chosen: a.pdf/)).toBeInTheDocument();
  });
});

describe("Import: filtering the statements", () => {
  const PICH = { account_id: 3, name: "Pichincha Mastercard Black", last4: "2829" };
  const stmt = (id: number, over: Partial<Statement>): Statement => ({
    ...base,
    statement_file_id: id,
    file_name: `s${id}.pdf`,
    can_read: true,
    ...over,
  });
  const ALL = [
    stmt(10, { file_name: "ESTADOCUENTA202610.pdf" }), // not read
    stmt(11, { accounts: [PICH], batch: { batch_id: 1, status: "preview", tieout_ok: true } }),
    stmt(12, { accounts: [PICH], batch: { batch_id: 2, status: "preview", tieout_ok: false } }),
    stmt(13, { accounts: [PICH], batch: { batch_id: 3, status: "approved", tieout_ok: true } }),
    stmt(14, { ...DINERS, statement_file_id: 14, file_name: "diners.pdf" }),
    stmt(15, { batch: { batch_id: 4, status: "rejected", tieout_ok: false } }), // discarded: read again
  ];

  it("knows where each statement stands", () => {
    expect(ALL.map(standing)).toEqual(["to_read", "waiting", "problems", "loaded", "attention", "to_read"]);
    expect(standing({ ...base, can_read: false })).toBe("attention");
    const f = (o: Partial<Parameters<typeof filterStatements>[1]>) =>
      filterStatements(ALL, { account: "", standing: "", text: "", ...o }).map((s) => s.statement_file_id);
    expect(f({ account: "3" })).toEqual([11, 12, 13]);
    expect(f({ account: "none" })).toEqual([14]);
    expect(f({ account: "3", standing: "problems" })).toEqual([12]);
    expect(f({ text: "202610" })).toEqual([10]);
    expect(f({ text: "diners" })).toEqual([14]); // the bank's name too
  });

  it("filters the list by account, status and name", async () => {
    listed = ALL;
    renderCard();
    expect(await screen.findByText("6 statements.")).toBeInTheDocument();
    const table = () => screen.getByRole("table", { name: "Uploaded statements" });
    fireEvent.change(screen.getByLabelText("Account"), { target: { value: "3" } });
    expect(screen.getByText("Showing 3 of 6 statements.")).toBeInTheDocument();
    const status = screen.getByLabelText("Status");
    expect(within(status).getByRole("option", { name: "Doesn’t tie out (1)" })).toBeInTheDocument();
    fireEvent.change(status, { target: { value: "loaded" } });
    expect(within(table()).getAllByRole("row")).toHaveLength(2); // header + s13
    expect(table()).toHaveTextContent("s13.pdf");
    fireEvent.change(screen.getByLabelText("File name"), { target: { value: "zzz" } });
    expect(screen.getByText("No statement matches these filters.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("6 statements.")).toBeInTheDocument();
    expect(screen.getByLabelText("Account")).toHaveValue("");
  });
});
