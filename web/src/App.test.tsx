import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { PAGES } from "./pages";

function mockApi(health: object, me: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(url.endsWith("/health") ? health : url.includes("/cashflow/") ? [] : me),
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

  it("shows the database as connected and the signed-in user", async () => {
    mockApi(okHealth, { name: "hernan@example.com", authenticated: true });
    renderAt("/");
    expect(await screen.findByText("Database connected")).toBeInTheDocument();
    expect(await screen.findByText("hernan@example.com")).toBeInTheDocument();
  });

  it("flags an unavailable database", async () => {
    mockApi(
      { ...okHealth, status: "degraded", database: "unavailable" },
      { name: null, authenticated: false },
    );
    renderAt("/status");
    expect(await screen.findByText("Database unavailable")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Data Status" })).toBeInTheDocument();
  });
});
