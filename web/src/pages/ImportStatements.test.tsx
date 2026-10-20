import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Statement } from "../api";
import { StatementsCard } from "./ImportStatements";

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

  it("accepts dropped files", async () => {
    renderCard();
    await screen.findByText("No statements uploaded yet.");
    const zone = screen.getByText("Drop statement PDFs here or choose files").closest("label")!;
    fireEvent.dragOver(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "a.pdf")] } });
    expect(screen.getByText(/1 file chosen: a.pdf/)).toBeInTheDocument();
  });
});
