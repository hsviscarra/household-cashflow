import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { BackupStatus } from "../api";
import { BackupPanel, backupLine, drillLine } from "./BackupPanel";

const OK: BackupStatus = {
  where: "azure",
  backup: {
    file: "db/cashflow-20261028-081700.bacpac",
    finished_at: "2026-10-28T08:18:30+00:00",
    size: 2_200_000,
    migration: "0018",
    rows: 18240,
    seconds: 40,
  },
  drill: { ok: true, finished_at: "2026-10-02T09:30:00+00:00", problems: [] },
  backup_overdue: false,
  drill_overdue: false,
  error: null,
};

function renderWith(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackupPanel />
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("backups panel", () => {
  it("words", () => {
    expect(backupLine(OK)).toMatch(/^Last backup Oct 28, 2026, \d+:18 [AP]M · 2\.1 MB · 18,240 rows$/);
    expect(backupLine({ ...OK, backup: { ...OK.backup!, size: 300 } })).toContain("· 1 KB ·");
    expect(backupLine({ ...OK, backup: null })).toBe("No backup yet.");
    expect(backupLine({ ...OK, where: "local", backup: null })).toBe("Backups run in Azure; none here.");
    expect(drillLine(OK)).toMatch(/restored and matched every table\.$/);
    expect(drillLine({ ...OK, drill: null })).toBe("No restore drill yet.");
    expect(
      drillLine({
        ...OK,
        drill: { ok: false, finished_at: OK.drill!.finished_at, problems: ["a.", "b.", "c."] },
      }),
    ).toMatch(/failed: a\. b\.$/);
  });

  it("healthy, overdue, local, unreadable and failing", async () => {
    const { unmount } = renderWith(OK);
    const panel = await screen.findByRole("region", { name: "Backups" });
    expect(panel.className).toContain("bg-good-bg");
    expect(panel).toHaveTextContent("restored and matched every table");
    unmount();
    const overdue = renderWith({ ...OK, backup_overdue: true, drill_overdue: true });
    const p2 = await screen.findByRole("region", { name: "Backups" });
    expect(p2.className).toContain("bg-attention-bg");
    expect(p2).toHaveTextContent("more than a day and a half ago");
    expect(p2).toHaveTextContent("More than 40 days ago.");
    overdue.unmount();
    const local = renderWith({ ...OK, where: "local", backup: null, drill: null, backup_overdue: true });
    const p3 = await screen.findByRole("region", { name: "Backups" });
    expect(p3.className).toContain("bg-info-bg");
    expect(p3).not.toHaveTextContent("restore drill");
    local.unmount();
    const broken = renderWith({ ...OK, error: "Backups can't be read: no route" });
    expect(await screen.findByText("Backups can't be read: no route")).toBeInTheDocument();
    broken.unmount();
    renderWith({ detail: "x" }, 500);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("region", { name: "Backups" })).toBeNull();
  });
});
