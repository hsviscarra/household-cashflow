import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Person, TransferNote } from "../api";
import { pickCategory } from "../test/pick";
import PeoplePage from "./People";

const CATEGORIES = [
  {
    category_id: 40,
    parent_id: null,
    name: "Transfers",
    kind: "transfer",
    color: null,
    is_fixed: false,
    is_active: true,
    sort_order: 0,
    children: [
      {
        category_id: 41,
        parent_id: 40,
        name: "Held for Others",
        kind: "transfer",
        color: null,
        is_fixed: false,
        is_active: true,
        sort_order: 0,
      },
    ],
  },
];

const RUBEN: Person = {
  counterparty_id: 7,
  name: "Rubén Miranda",
  patterns: "RUBEN MIRANDA; NAPOLES",
  category_id: 41,
  category_path: "Transfers / Held for Others",
  holding_id: 3,
  holding_name: "Holding for Rubén Miranda",
  is_active: true,
  notes: null,
  lines: 4,
  received: "12430.00",
  paid: "3150.00",
};

const note = (over: Partial<TransferNote>): TransferNote => ({
  note_id: 1,
  txn_date: "2026-10-15",
  amount: "561.89",
  account_id: 5,
  account_name: "Produbanco Ahorros Hernan",
  counterparty_id: 7,
  person: "Rubén Miranda",
  category_id: null,
  category_path: null,
  other_party: "INTELLIGENT ENTERPRISE MANAG",
  description: "pago obra",
  share: null,
  source: "email",
  transaction_id: null,
  line_date: null,
  line_description: null,
  created_by: "gmail",
  ...over,
});

let people: Person[];
let notes: TransferNote[];
let calls: { method: string; url: string; body?: unknown }[];
const json = (v: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(v), { status }));

beforeEach(() => {
  calls = [];
  people = [RUBEN];
  notes = [
    note({ share: "300.00" }),
    note({
      note_id: 2,
      amount: "-25.00",
      person: null,
      counterparty_id: null,
      other_party: null,
      description: null,
      source: "manual",
      transaction_id: 99,
      line_date: "2026-10-14",
      line_description: "TRANSFERENCIA",
      category_path: "Family Support / Money to Family",
      account_name: null,
    }),
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, url, body });
      if (url === "/api/categories") return json(CATEGORIES);
      if (url === "/api/people" && method === "GET") return json(people);
      if (url === "/api/people" && method === "POST") {
        const made = { ...RUBEN, counterparty_id: 8, name: body.name, lines: 2, holding_name: null };
        people = [...people, made];
        return json(made, 201);
      }
      if (url === "/api/people/7" && method === "PATCH") return json({ ...RUBEN, ...body });
      if (url === "/api/people/7" && method === "DELETE") {
        people = [];
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url === "/api/people/7/lines")
        return json([
          {
            transaction_id: 5,
            txn_date: "2026-07-02",
            amount: "12430.00",
            description: "TRANSFER RUBEN MIRANDA",
            account_name: "BofA Adv Plus Banking",
            category_path: "Transfers / Held for Others",
            notes: null,
          },
        ]);
      if (url.startsWith("/api/transfer-notes?")) return json(notes);
      if (url === "/api/transfer-notes" && method === "POST")
        return json(
          note({
            note_id: 3,
            transaction_id: 50,
            line_date: "2026-11-04",
            line_description: "TRANSFERENCIA",
          }),
          201,
        );
      if (url === "/api/transfer-notes/match") return json({ matched: 1, tagged: 2 });
      if (url.startsWith("/api/transfer-notes/") && method === "DELETE")
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/api/accounts")
        return json([
          { account_id: 5, name: "Produbanco Ahorros Hernan", kind: "savings", is_active: true },
          { account_id: 6, name: "Capital One Venture", kind: "credit_card", is_active: true },
        ]);
      if (url === "/api/networth")
        return json({
          items: [
            { name: "Remaining to pay Ruben", holding_class: "personal_loan", holding_id: 3 },
            { name: "Car", holding_class: "vehicle", holding_id: 4 },
          ],
        });
      return json({ detail: `unexpected ${method} ${url}` }, 500);
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PeoplePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("People & transfers", () => {
  it("saves a note and says what it matched", async () => {
    renderPage();
    const form = await screen.findByRole("form", { name: "Tell the app about a transfer" });
    fireEvent.click(within(form).getByText("I received"));
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "561.89" } });
    fireEvent.change(within(form).getByLabelText("Date"), { target: { value: "2026-11-04" } });
    fireEvent.change(within(form).getByLabelText("For whom"), { target: { value: "7" } });
    await waitFor(() => expect(within(form).getAllByRole("option").length).toBeGreaterThan(2));
    fireEvent.change(within(form).getByLabelText("Account (optional)"), { target: { value: "5" } });
    // Cards don't receive transfers: only bank accounts are offered.
    expect(within(form).queryByText("Capital One Venture")).toBeNull();
    pickCategory(within(form).getByRole("combobox", { name: /Category/ }), "held", /Held for Others/);
    fireEvent.change(within(form).getByLabelText(/Their share/), { target: { value: "852" } });
    expect(within(form).getByRole("combobox", { name: "Category for your part" })).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("What it was for"), { target: { value: "pago obra" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save the note" }));
    await screen.findByText(/Saved and matched to the Nov 4 line: TRANSFERENCIA/);
    const post = calls.find((c) => c.method === "POST" && c.url === "/api/transfer-notes");
    expect(post?.body).toEqual({
      txn_date: "2026-11-04",
      direction: "received",
      amount: "561.89",
      counterparty_id: 7,
      account_id: 5,
      category_id: 41,
      description: "pago obra",
      share: "852",
    });
  });

  it("lists notes, matches again and deletes", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "Transfer notes" });
    expect(within(list).getByText(/Waiting for its statement/)).toBeTruthy();
    expect(within(list).getByText(/from the bank's email/)).toBeTruthy();
    expect(within(list).getByText(/their share 300.00/)).toBeTruthy();
    expect(within(list).getByText(/Matched: Oct 14 TRANSFERENCIA/)).toBeTruthy();
    expect(within(list).getByText(/Someone/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Match again" }));
    await screen.findByText("Matched 1 note; named 2 more lines.");
    fireEvent.click(within(list).getByRole("button", { name: "Delete note 2" }));
    await screen.findByText(/Note deleted/);
  });

  it("adds a person with a new balance, shows lines, edits and removes", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "People" });
    const card = within(list).getByText("Rubén Miranda").closest("li")!;
    expect(within(card).getByText(/4 lines · received 12,430.00 · paid 3,150.00/)).toBeTruthy();
    expect(within(card).getByText(/balance: Holding for Rubén Miranda/)).toBeTruthy();
    expect(
      within(card).getByRole("link", { name: "In Transactions (12 months)" }).getAttribute("href"),
    ).toMatch(/^\/transactions\?cp=\d+&months=12$/);
    fireEvent.click(within(card).getByRole("button", { name: "Show lines" }));
    await within(card).findByText(/TRANSFER RUBEN MIRANDA/);

    fireEvent.click(screen.getByRole("button", { name: "Add a person" }));
    const form = screen.getByRole("form", { name: "New person" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Gabriel" } });
    fireEvent.change(within(form).getByLabelText(/Texts to find/), { target: { value: "GABRIEL" } });
    fireEvent.change(within(form).getByLabelText(/What you hold for them today/), {
      target: { value: "1468.80" },
    });
    fireEvent.change(within(form).getByLabelText("As of"), { target: { value: "2026-11-05" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await screen.findByText("Gabriel saved: 2 lines are theirs.");
    const post = calls.find((c) => c.method === "POST" && c.url === "/api/people");
    expect(post?.body).toMatchObject({
      name: "Gabriel",
      patterns: "GABRIEL",
      new_balance: true,
      opening_balance: "1468.80",
      opening_as_of: "2026-11-05",
      holding_id: null,
    });

    fireEvent.click(within(card).getByRole("button", { name: "Edit" }));
    const edit = screen.getByRole("form", { name: "Edit Rubén Miranda" });
    // Only personal loans can be a person's balance.
    expect(within(edit).queryByText("Car")).toBeNull();
    fireEvent.change(within(edit).getByLabelText("Balance on Debt & Net Worth"), { target: { value: "" } });
    fireEvent.click(within(edit).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ holding_id: null }),
    );

    vi.spyOn(window, "confirm").mockReturnValue(true);
    const again = within(await screen.findByRole("list", { name: "People" }))
      .getByText("Rubén Miranda")
      .closest("li")!;
    fireEvent.click(within(again).getByRole("button", { name: "Remove" }));
    await screen.findByText(/removed; their lines keep their categories/);
  });

  it("says when saving fails", async () => {
    renderPage();
    const form = await screen.findByRole("form", { name: "Tell the app about a transfer" });
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "5" } });
    vi.mocked(fetch).mockImplementationOnce(() => json({ detail: "Account not found." }, 404));
    fireEvent.click(within(form).getByRole("button", { name: "Save the note" }));
    await screen.findByText("Account not found.");
  });
});
