import { expect, test } from "@playwright/test";

// Runs after the statement, workbook and recurring specs: the next three months are on screen.
test("projections: the next three months, cash day by day, alerts", async ({ page }) => {
  await page.goto("/projections");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Next 3 months: [−+]?[\d,]+\.\d{2}/);
  const table = page.getByRole("table", { name: "Projection for the next 3 months" });
  await expect(table.getByRole("columnheader")).toHaveCount(4);
  await expect(table.getByRole("row", { name: /^Cash at month end/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /^Projected cash from/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Spending alerts" })).toBeVisible();
  // ADR-033: the assumptions, the what-ifs and a longer horizon.
  await expect(page.getByRole("heading", { name: "How it’s calculated" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What if…" })).toBeVisible();
  await page.getByRole("group", { name: "Horizon" }).getByRole("button", { name: "12 months" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Next 12 months/);
  await page.getByRole("group", { name: "Horizon" }).getByRole("button", { name: "3 months" }).click();
});
