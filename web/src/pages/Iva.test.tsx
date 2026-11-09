import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { IvaMonth } from "../api";
import IvaPage from "./Iva";

const R: IvaMonth = {
  person: "Hernan",
  month: "2026-09-01",
  sales: [
    {
      number: "001-002-53",
      issue_date: "2026-09-29",
      buyer_name: "CLIENTE DE PRUEBA S.A.",
      base_taxed: "2808.70",
      base_zero: "0",
      tax: "421.31",
      total: "3230.01",
      income_tax_withheld: "280.87",
      iva_withheld: "421.31",
    },
  ],
  purchases: [
    {
      invoice_id: 1,
      issuer_ruc: "1791111111001",
      issuer_name: "INTERNET DE PRUEBA",
      number: "1",
      issue_date: "2026-09-01",
      base_taxed: "34.99",
      base_zero: "0",
      tax: "5.25",
      total: "40.24",
      iva_use: null,
      access_key: "k",
    },
  ],
  withholdings: [],
  form: { f401: "3308.70", f421: "496.31", f620: "0", f617: "1417.26" },
  opening_month: null,
  unclassified: 1,
  income_tax_withheld: "280.87",
  notes: ["Enter the credit carried in"],
};

let calls: { method: string; url: string; body: unknown }[];
beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (method === "PUT") return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(new Response(JSON.stringify(R), { status: 200 }));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Monthly IVA", () => {
  it("shows the return, asks for the carried credit and how an issuer counts", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/taxes/iva?month=2026-09"]}>
          <IvaPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Form 104 · September 2026")).toBeInTheDocument();
    expect(screen.getByText("1,417.26")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the workbook" })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/taxes/iva/excel?month=2026-09"),
    );
    fireEvent.change(screen.getByLabelText("How INTERNET DE PRUEBA counts"), { target: { value: "business" } });
    await waitFor(() => expect(calls.some((c) => c.url === "/api/taxes/iva/issuers")).toBe(true));
    expect(calls.find((c) => c.url === "/api/taxes/iva/issuers")!.body).toEqual({
      issuer_ruc: "1791111111001",
      iva_use: "business",
    });
    fireEvent.change(screen.getByLabelText("617 · retenciones"), { target: { value: "1,462.79" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/taxes/iva/opening")).toBe(true));
    expect(calls.find((c) => c.url === "/api/taxes/iva/opening")!.body).toMatchObject({
      person: "Hernan",
      month: "2026-09",
      retention_credit: "1462.79",
    });
  });
});
