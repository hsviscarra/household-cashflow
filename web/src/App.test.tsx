import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App, { WAKE_MS, databasePill } from "./App";
import { PAGES } from "./pages";

function mockApi(health: object, me: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            url.endsWith("/health")
              ? health
              : url.includes("/cashflow/")
                ? []
                : url.includes("/api/review")
                  ? { month: null, groups: [], uncategorized_lines: 12, suggestions_available: false }
                  : me,
          ),
          {
            status: url.endsWith("/health") && (health as { database: string }).database !== "ok" ? 503 : 200,
          },
        ),
      ),
    ),
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

  it("lists every page in the navigation", () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    for (const page of PAGES) {
      expect(screen.getByRole("link", { name: page.label })).toBeInTheDocument();
    }
  });

  it("groups the sidebar and counts the Inbox", async () => {
    mockApi(okHealth, { name: null, authenticated: false });
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const group of ["Analyze", "Daily", "Plan", "Reports"]) {
      expect(within(nav).getByText(group)).toBeInTheDocument();
    }
    const inbox = within(nav).getByRole("link", { name: /^Inbox/ });
    expect(inbox).toHaveAttribute("href", "/review");
    expect(await within(inbox).findByText("12")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Upload statements" })).toHaveAttribute("href", "/import");
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
