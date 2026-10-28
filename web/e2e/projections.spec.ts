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
});
