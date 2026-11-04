import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Account, CategoryGroup, Rule } from "../api";
import Settings, { usage } from "./Settings";
import { pickCategory } from "../test/pick";

// Small in-memory stand-in for the F1 API, so the page is tested against real request shapes.
type Db = { accounts: Account[]; categories: CategoryGroup[]; rules: Rule[] };
let db: Db;
let calls: { method: string; url: string; body: unknown }[];

function seed(): Db {
  return {
    accounts: [
      {
        account_id: 1,
        name: "Capital One Venture",
        institution: "Capital One",
        kind: "credit_card",
        owner: "Joint",
        country: "US",
        last4: "4003",
        is_active: true,
      },
    ],
    categories: [
      {
        category_id: 10,
        parent_id: null,
        name: "Dining",
        kind: "expense",
        color: "#E2583E",
        is_fixed: false,
        is_active: true,
        sort_order: 0,
        children: [
          {
            category_id: 11,
            parent_id: 10,
            name: "Food Delivery",
            kind: "expense",
            color: null,
            is_fixed: false,
            is_active: true,
            sort_order: 0,
            description: "Ready meals delivered: Uber Eats.",
            lines: 12,
            rules: 1,
          },
        ],
      },
      {
        category_id: 30,
        parent_id: null,
        name: "Groceries",
        kind: "expense",
        color: "#4E9A2A",
        is_fixed: false,
        is_active: true,
        sort_order: 1,
        children: [],
      },
      {
        category_id: 20,
        parent_id: null,
        name: "Salary",
        kind: "income",
        color: "#4E9A2A",
        is_fixed: false,
        is_active: true,
        sort_order: 1,
        children: [],
      },
    ],
    rules: [
      {
        rule_id: 100,
        pattern: "UBER EATS",
        match_type: "contains",
        category_id: 11,
        category_path: "Dining / Food Delivery",
        priority: 20,
        is_active: true,
        amount_min: null,
        amount_max: null,
      },
    ],
  };
}

const json = (data: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status }));

function fakeFetch(input: string, init?: RequestInit) {
  const method = init?.method ?? "GET";
  const body = init?.body ? JSON.parse(init.body as string) : undefined;
  calls.push({ method, url: input, body });
  const url = new URL(input, "http://test");
  const path = url.pathname;

  if (path === "/api/accounts" && method === "GET") return json(db.accounts);
  if (path === "/api/accounts" && method === "POST") {
    if (db.accounts.some((a) => a.name === body.name))
      return json({ detail: `An account named '${body.name}' already exists.` }, 409);
    const a = { account_id: db.accounts.length + 1, ...body };
    db.accounts.push(a);
    return json(a, 201);
  }
  const acc = path.match(/^\/api\/accounts\/(\d+)$/);
  if (acc && method === "PATCH") {
    const a = db.accounts.find((x) => x.account_id === Number(acc[1]))!;
    Object.assign(a, body);
    return json(a);
  }
  if (path === "/api/categories" && method === "GET") return json(db.categories);
  if (path === "/api/categories" && method === "POST") {
    const parent = db.categories.find((g) => g.category_id === body.parent_id);
    const c = {
      category_id: 500 + calls.length,
      parent_id: body.parent_id ?? null,
      name: body.name,
      kind: parent?.kind ?? body.kind,
      color: body.color ?? null,
      is_fixed: false,
      is_active: true,
      sort_order: 9,
    };
    if (parent) parent.children.push(c);
    else db.categories.push({ ...c, children: [] });
    return json(c, 201);
  }
  const one = path.match(/^\/api\/categories\/(\d+)$/);
  if (one && method === "PATCH") {
    const all = db.categories.flatMap((g) => [g, ...g.children]);
    const c = all.find((x) => x.category_id === Number(one[1]))!;
    Object.assign(c, body);
    if (body.parent_id) {
      db.categories.forEach((g) => (g.children = g.children.filter((x) => x.category_id !== c.category_id)));
      db.categories.find((g) => g.category_id === body.parent_id)!.children.push(c);
    }
    return json(c);
  }
  if (path === "/api/merchant-rules" && method === "GET") return json(db.rules);
  if (path === "/api/merchant-rules/test") {
    const d = url.searchParams.get("description")!.toUpperCase();
    return json({ description: d, rule: db.rules.find((r) => d.includes(r.pattern)) ?? null });
  }
  if (path === "/api/merchant-rules" && method === "POST") {
    const r = {
      rule_id: 200,
      is_active: true,
      category_path: "Salary",
      ...body,
      applied: 4,
    };
    db.rules.push(r);
    return json(r, 201);
  }
  const rule = path.match(/^\/api\/merchant-rules\/(\d+)$/);
  if (rule && method === "PATCH") {
    const r = db.rules.find((x) => x.rule_id === Number(rule[1]))!;
    Object.assign(r, body);
    return json(r);
  }
  if (rule && method === "DELETE") {
    db.rules = db.rules.filter((x) => x.rule_id !== Number(rule[1]));
    return Promise.resolve(new Response(null, { status: 204 }));
  }
  return json({ detail: "not found" }, 404);
}

function renderSettings(tab = "accounts") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`/settings?tab=${tab}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Settings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  db = seed();
  calls = [];
  vi.stubGlobal("fetch", vi.fn(fakeFetch));
});
afterEach(() => vi.unstubAllGlobals());

describe("Settings: accounts", () => {
  it("lists accounts with the last four digits masked", async () => {
    renderSettings();
    expect(await screen.findByText("Capital One Venture")).toBeInTheDocument();
    expect(screen.getByText(/•••• 4003/)).toBeInTheDocument();
  });

  it("rejects a full card number before sending it", async () => {
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Add account" }));
    fireEvent.change(screen.getByLabelText(/Last 4 digits/), { target: { value: "44" } });
    expect(screen.getByText("Enter exactly four digits.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add account" }).at(-1)).toBeDisabled();
  });

  it("adds an account and confirms it", async () => {
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Add account" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "IBKR" } });
    fireEvent.change(screen.getByLabelText("Institution"), {
      target: { value: "Interactive Brokers" },
    });
    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "Hernan" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    expect(await screen.findByText("Account added: IBKR.")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({ name: "IBKR", last4: null, owner: "Hernan" });
    expect(await screen.findByText("IBKR")).toBeInTheDocument();
  });

  it("shows the API's message when a save fails", async () => {
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Add account" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Capital One Venture" } });
    fireEvent.change(screen.getByLabelText("Institution"), { target: { value: "Capital One" } });
    fireEvent.click(screen.getByRole("button", { name: "Add account" }));
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
  });

  it("edits an account inline", async () => {
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Edit Capital One Venture" }));
    fireEvent.click(screen.getByLabelText(/^Active/));
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));
    expect(await screen.findByText("Inactive")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.url).toBe("/api/accounts/1");
  });

  it("records the day a card was suspended", async () => {
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Edit Capital One Venture" }));
    fireEvent.change(screen.getByLabelText("Closed or suspended on (optional)"), {
      target: { value: "2026-09-15" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));
    expect(await screen.findByText("Closed Sep 15, 2026")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "PATCH")?.body as Record<string, unknown>;
    expect(sent.closed_on).toBe("2026-09-15");
  });
});

describe("Settings: categories", () => {
  it("groups categories by kind and adds a subcategory", async () => {
    renderSettings("categories");
    expect(await screen.findByRole("heading", { name: "Expenses" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Income" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1 subcategory in Dining/ }));
    fireEvent.change(screen.getByLabelText("New subcategory in Dining"), {
      target: { value: "Coffee" },
    });
    const diningForm = screen.getByLabelText("New subcategory in Dining").closest("form")!;
    fireEvent.click(within(diningForm).getByRole("button", { name: "Add subcategory" }));
    expect(await screen.findByText("Subcategory added: Dining / Coffee.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      name: "Coffee",
      parent_id: 10,
    });
  });
});

describe("Settings: category descriptions", () => {
  it("shows what goes in each category and edits it", async () => {
    renderSettings("categories");
    fireEvent.click(await screen.findByRole("button", { name: /1 subcategory in Dining/ }));
    expect(await screen.findByText("Ready meals delivered: Uber Eats.")).toBeInTheDocument();
    expect(screen.getAllByText("No description yet: Edit to say what goes here.").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Edit Food Delivery" }));
    const about = screen.getByLabelText("What goes here");
    expect(about).toHaveValue("Ready meals delivered: Uber Eats.");
    fireEvent.change(about, { target: { value: "  Delivered meals, not groceries.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save category" }));
    expect(await screen.findByText("Category saved: Food Delivery.")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "PATCH")?.body as Record<string, unknown>;
    expect(sent.description).toBe("Delivered meals, not groceries.");
    expect(await screen.findByText("Delivered meals, not groceries.")).toBeInTheDocument();
  });
});

describe("Settings: finding and organizing categories", () => {
  it("collapses groups, shows how much each is used, and finds by description", async () => {
    renderSettings("categories");
    const toggle = await screen.findByRole("button", { name: /1 subcategory in Dining/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Food Delivery")).toBeNull();
    // The group counts its subcategories' lines.
    const dining = toggle.closest("li")!;
    expect(dining).toHaveTextContent("12 lines");
    expect(screen.getAllByText("Not used yet").length).toBeGreaterThan(0); // Groceries, Salary
    fireEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(screen.getByText("12 lines · 1 rule")).toBeInTheDocument(); // Food Delivery itself
    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByText("Food Delivery")).toBeNull();

    // "uber" is only in Food Delivery's description: Dining opens with it; other groups hide.
    fireEvent.change(screen.getByLabelText("Find a category"), { target: { value: "UBER" } });
    expect(screen.getByText("1 group matches “UBER”.")).toBeInTheDocument();
    expect(screen.getByText("Food Delivery")).toBeInTheDocument();
    expect(screen.queryByText("Salary")).toBeNull();
    expect(screen.queryByRole("button", { name: "Expand all" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Find a category"), { target: { value: "zzz" } });
    expect(screen.getByText("Nothing matches “zzz”.")).toBeInTheDocument();
  });

  it("moves a subcategory to another group of the same kind", async () => {
    renderSettings("categories");
    fireEvent.click(await screen.findByRole("button", { name: /1 subcategory in Dining/ }));
    fireEvent.click(screen.getByRole("button", { name: "Edit Food Delivery" }));
    const group = screen.getByLabelText("In the group");
    // Only spending groups: Salary (income) isn't offered.
    expect(
      within(group)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Dining", "Groceries"]);
    fireEvent.change(group, { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save category" }));
    expect(
      await screen.findByText("Moved Food Delivery to Groceries; its lines and rules moved with it."),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "PATCH")?.body as Record<string, unknown>;
    expect(sent.parent_id).toBe(30);
    expect(await screen.findByRole("button", { name: /1 subcategory in Groceries/ })).toBeInTheDocument();
  });

  it("describes usage in words", () => {
    expect(usage(0, 0)).toBe("Not used yet");
    expect(usage(1, 0)).toBe("1 line");
    expect(usage(0, 2)).toBe("2 rules");
    expect(usage(1234, 1)).toBe("1,234 lines · 1 rule");
  });
});

describe("Settings: merchant rules", () => {
  it("tests a description against the rules", async () => {
    renderSettings("rules");
    const input = await screen.findByLabelText("Try a statement description");
    fireEvent.change(input, { target: { value: "uber eats san jose" } });
    fireEvent.click(screen.getByRole("button", { name: "Test rules" }));
    expect(await screen.findByText("Dining / Food Delivery", { selector: "strong" })).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "PAY*MAURICIO" } });
    fireEvent.click(screen.getByRole("button", { name: "Test rules" }));
    expect(await screen.findByText(/would go to review/)).toBeInTheDocument();
  });

  it("adds, switches off and deletes a rule", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderSettings("rules");
    fireEvent.click(await screen.findByRole("button", { name: "Add rule" }));
    fireEvent.change(screen.getByLabelText("Pattern in the statement description"), {
      target: { value: " KENILITY " },
    });
    pickCategory(screen.getByRole("combobox", { name: "Category" }), "salary", "Salary");
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    expect(
      await screen.findByText(
        "Rule added: KENILITY → Salary. It categorized 4 lines that needed a category.",
      ),
    ).toBeInTheDocument();

    const table = screen.getByRole("table");
    fireEvent.click(await within(table).findByLabelText("Rule UBER EATS active"));
    expect(await screen.findByText("Rule turned off: UBER EATS.")).toBeInTheDocument();

    fireEvent.click(within(table).getByRole("button", { name: "Delete rule UBER EATS" }));
    expect(await screen.findByText("Rule deleted: UBER EATS.")).toBeInTheDocument();
    await waitFor(() => expect(within(table).queryByText("UBER EATS")).not.toBeInTheDocument());
  });

  it("filters the rule list", async () => {
    renderSettings("rules");
    fireEvent.change(await screen.findByLabelText("Filter rules"), { target: { value: "zzz" } });
    expect(screen.getByText(/No rules match/)).toBeInTheDocument();
  });
});
