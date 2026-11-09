import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App, { FAMILIES, WAKE_MS, databasePill } from "./App";
import { PAGES } from "./pages";

const EMPTY_FLOWS = {
  month: "2026-11-01",
  prev_month: "2026-10-01",
  months: [],
  source: "none",
  flows: [],
  trend: [],
};

function mockApi(health: object, me: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = (data: unknown, status = 200) =>
        Promise.resolve(new Response(JSON.stringify(data), { status }));
      if (url.endsWith("/health"))
        return body(health, (health as { database: string }).database !== "ok" ? 503 : 200);
      if (url.startsWith("/api/cashflow/flows")) return body(EMPTY_FLOWS);
      if (url.startsWith("/api/review"))
        return body({ month: null, groups: [], uncategorized_lines: 12, suggestions_available: false });
      if (url === "/api/todo") return body({ today: "2026-11-08", total: 12, sections: [] });
      if (url.startsWith("/api/me/settings")) return body({ user: "local", settings: {} });
      if (url === "/api/me") return body(me);
      return body({ detail: "not here" }, 404);
    }),
  );
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const okHealth = { status: "ok", version: "0.1.0", git_sha: "abc", environment: "test", database: "ok" };

afterEach(() => vi.unstubAllGlobals());

describe("App shell", () => {
  it("shows the empty overview with a way to load the history", async () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "No cash flow yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Load the Excel history" })).toHaveAttribute("href", "/import");
  });

  it("lists every page in the sidebar or as a tab of one (ADR-060)", () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Main" });
    const tabs = new Set(FAMILIES.flatMap((f) => f.tabs.map(([p]) => p)));
    for (const page of PAGES.filter((p) => !p.hidden && !tabs.has(p.path) && p.path !== "/import")) {
      expect(within(nav).getByRole("link", { name: page.label })).toBeInTheDocument();
    }
    for (const f of FAMILIES) expect(within(nav).getByRole("link", { name: f.label })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Groceries" })).not.toBeInTheDocument();
  });

  it("shows a family's tabs and keeps its sidebar item current", () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/groceries");
    const tabs = screen.getByRole("navigation", { name: "Spending pages" });
    expect(within(tabs).getByRole("link", { name: "Groceries" })).toHaveAttribute("aria-current", "page");
    expect(within(tabs).getByRole("link", { name: "Purchases (invoices)" })).toHaveAttribute("href", "/purchases");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Spending" }).className).toContain("bg-nav-active");
  });

  it("groups the sidebar and counts what's to do", async () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const group of ["Money", "Wealth", "Plan", "Taxes & reports"]) {
      expect(within(nav).getByText(group)).toBeInTheDocument();
    }
    const todo = within(nav).getByRole("link", { name: /^To do/ });
    expect(todo).toHaveAttribute("href", "/todo");
    expect(await within(todo).findByText("12")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Upload statements" })).toHaveAttribute("href", "/import");
  });

  it("switches between light, dark and the device's theme", async () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    await screen.findByRole("heading", { name: "No cash flow yet" }); // settings loaded
    const group = screen.getByRole("radiogroup", { name: "Theme" });
    expect(within(group).getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(group).getByRole("radio", { name: "Dark" }));
    await vi.waitFor(() => expect(document.documentElement.getAttribute("data-theme")).toBe("dark"));
    fireEvent.click(within(group).getByRole("radio", { name: "Auto" }));
    await vi.waitFor(() => expect(document.documentElement.hasAttribute("data-theme")).toBe(false));
  });

  it("opens and closes the menu on a phone", () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    const button = screen.getByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Close" })).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("link", { name: "Spending" }));
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });

  it("shows the database as connected and the signed-in user", async () => {
    mockApi(okHealth, { name: "hernan@example.com", authenticated: true });
    renderAt("/");
    expect(await screen.findByText("Database connected")).toBeInTheDocument();
    expect(await screen.findByText("hernan@example.com")).toBeInTheDocument();
  });

  it("shows a paused database as waking up, and unavailable after two minutes", async () => {
    mockApi(
      { ...okHealth, status: "degraded", database: "unavailable" },
      { name: null, authenticated: false },
    );
    renderAt("/no-such-page");
    expect(await screen.findByText("Database waking up…")).toBeInTheDocument();
    expect(databasePill("unavailable", WAKE_MS + 1)).toEqual({
      label: "Database unavailable",
      className: "pill-bad",
    });
    expect(databasePill("ok", WAKE_MS + 1).label).toBe("Database connected");
  });
});
