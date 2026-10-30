import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Purchases } from "../api";
import PurchasesPage, { coverageLine } from "./Purchases";

const P: Purchases = {
  month: "2026-10",
  total: "31.96",
  matched_total: "15.98",
  groups: [
    { group: "Household & Cleaning", amount: "14.96", lines: 2 },
    { group: "Dairy & Eggs", amount: "4.20", lines: 2 },
    { group: "Not grouped yet", amount: "4.80", lines: 2 },
  ],
  to_group: [
    {
      product_key: "YOG TONI FRUT 1L",
      description: "YOG TONI FRUT 1L",
      lines: 2,
      amount: "4.80",
      suggested_group: null,
    },
    {
      product_key: "LECHE ENTERA 1L",
      description: "LECHE ENTERA 1L",
      lines: 2,
      amount: "4.20",
      suggested_group: "Dairy & Eggs",
    },
  ],
  invoices: [
    {
      invoice_id: 1,
      issuer_name: "SUPER PRUEBA",
      number: "072-140-000123456",
      issue_date: "2026-10-28",
      subtotal: "15.00",
      tax: "0.98",
      total: "15.98",
      received_by: "gmail (infoedoc@vendor.example)",
      paid_with: {
        transaction_id: 9,
        txn_date: "2026-10-29",
        account: "Capital One Venture",
        description: "SUPER",
      },
      lines: [
        {
          line_no: 1,
          description: "LECHE ENTERA 1L",
          product_key: "LECHE ENTERA 1L",
          quantity: "2.000000",
          unit_price: "1.050000",
          total: "2.10",
          product_group: "Dairy & Eggs",
          group_source: "keyword",
        },
      ],
    },
    {
      invoice_id: 2,
      issuer_name: "FARMACIA PRUEBA",
      number: "001-001-000000001",
      issue_date: "2026-10-30",
      subtotal: "15.98",
      tax: "0",
      total: "15.98",
      received_by: "hernan@example.com",
      paid_with: null,
      lines: [],
    },
  ],
  product_groups: ["Dairy & Eggs", "Household & Cleaning", "Other"],
  suggestions_available: true,
};

function renderWith(data: Purchases | Response, posts: Record<string, Response> = {}) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}${typeof init?.body === "string" ? ` ${init.body}` : ""}`);
      if (method !== "GET") {
        const path = url.split("?")[0];
        return Promise.resolve(posts[`${method} ${path}`] ?? new Response("{}"));
      }
      return Promise.resolve(data instanceof Response ? data : new Response(JSON.stringify(data)));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/purchases?month=2026-10"]}>
        <PurchasesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

describe("purchases", () => {
  it("summarizes coverage", () => {
    expect(coverageLine(P)).toBe("2 invoices, 1 matched to the card or bank line that paid them.");
    expect(coverageLine({ ...P, invoices: [] })).toBe("No invoices for this month yet.");
    expect(coverageLine({ ...P, invoices: [P.invoices[0]] })).toBe(
      "1 invoice, 1 matched to the card or bank line that paid it.",
    );
  });

  it("shows the month by group, the invoices and their products", async () => {
    const calls = renderWith(P);
    expect(
      await screen.findByRole("heading", { level: 1, name: "What you bought in October 2026: 31.96" }),
    ).toBeInTheDocument();
    expect(calls[0]).toBe("GET /api/invoices?month=2026-10");
    const groups = screen.getByRole("region", { name: "By product group" });
    const rows = within(groups).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Household & Cleaning47%14.96");
    expect(rows[3]).toHaveTextContent("Not grouped yet15%4.80");

    const list = screen.getByRole("region", { name: "Invoices" });
    expect(list).toHaveTextContent("Paid with Capital One Venture on Oct 29");
    expect(list).toHaveTextContent("Payment not found yet");
    fireEvent.click(within(list).getByRole("button", { name: /SUPER PRUEBA/ }));
    expect(within(list).getByRole("table")).toHaveTextContent("LECHE ENTERA 1L21.052.10Dairy & Eggs");
    expect(list).toHaveTextContent("Invoice 072-140-000123456: 15.00 before tax, IVA 0.98");
  });

  it("confirms a product's group, starting from the suggestion", async () => {
    const calls = renderWith(P, {
      "PUT /api/invoices/products": new Response(
        JSON.stringify({ product_key: "LECHE ENTERA 1L", product_group: "Dairy & Eggs", lines_updated: 2 }),
      ),
    });
    const section = await screen.findByRole("region", { name: "Products to group" });
    expect(section).toHaveTextContent("2 products need a group");
    expect(section).toHaveTextContent("4.20 on 2 invoices; suggested Dairy & Eggs");
    const buttons = within(section).getAllByRole("button", { name: "Save group" });
    expect(buttons[0]).toBeDisabled(); // nothing chosen for the yogurt yet
    fireEvent.click(buttons[1]);
    await waitFor(() =>
      expect(calls).toContain(
        'PUT /api/invoices/products {"product_key":"LECHE ENTERA 1L","product_group":"Dairy & Eggs"}',
      ),
    );
    expect(await within(section).findByText("LECHE ENTERA 1L: saved as Dairy & Eggs.")).toBeInTheDocument();
    fireEvent.change(within(section).getByLabelText("Group for YOG TONI FRUT 1L"), {
      target: { value: "Other" },
    });
    expect(buttons[0]).toBeEnabled();
  });

  it("asks Claude and uploads XMLs", async () => {
    const calls = renderWith(P, {
      "POST /api/invoices/suggest": new Response(JSON.stringify({ products: 1 })),
      "POST /api/invoices": new Response(
        JSON.stringify([
          { file_name: "a.xml", outcome: "stored", message: "SUPER PRUEBA: 4 products", invoice_id: 3 },
          { file_name: "b.xml", outcome: "skipped", message: "A credit note.", invoice_id: null },
        ]),
      ),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Ask Claude about 1 products" }));
    expect(
      await screen.findByText("Claude suggested a group for 1 product. Confirm each one below."),
    ).toBeInTheDocument();
    expect(calls).toContain("POST /api/invoices/suggest?month=2026-10");

    fireEvent.change(screen.getByLabelText("Invoice XML files"), {
      target: { files: [new File(["<x/>"], "a.xml"), new File(["<x/>"], "b.xml")] },
    });
    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(results).toHaveTextContent("Added: a.xml SUPER PRUEBA: 4 products");
    expect(results).toHaveTextContent("Not an invoice: b.xml A credit note.");
  });

  it("explains errors and an empty month", async () => {
    renderWith(new Response(JSON.stringify({ detail: "Months look like 2026-10." }), { status: 422 }));
    expect(await screen.findByText(/Could not load the purchases/)).toBeInTheDocument();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    renderWith({ ...P, invoices: [], groups: [], to_group: [], total: "0" }, {});
    expect(await screen.findByText("No invoices for this month yet.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Purchases in October 2026");
  });

  it("shows a failed upload or suggestion", async () => {
    renderWith(P, {
      "POST /api/invoices/suggest": new Response(JSON.stringify({ detail: "Claude suggestions are off." }), {
        status: 503,
      }),
      "POST /api/invoices": new Response(JSON.stringify({ detail: "Upload at most 100 files at a time." }), {
        status: 422,
      }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "Ask Claude about 1 products" }));
    expect(await screen.findByText("Claude suggestions are off.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Invoice XML files"), {
      target: { files: [new File(["<x/>"], "a.xml")] },
    });
    expect(await screen.findByText("Upload at most 100 files at a time.")).toBeInTheDocument();
  });
});
