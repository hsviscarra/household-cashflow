import { expect, test } from "@playwright/test";

// Runs after the workbook and statement specs: January 2026 comes from the synthetic sheet, July
// 2026 from the synthetic Produbanco statement.
test("spending: a sheet month drills to its rows, a statement month lists merchants", async ({ page }) => {
  await page.goto("/spending?month=2026-01");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /^In January 2026 you spent [\d,]+\.\d{2}/,
  );
  await expect(page.getByText("From the Cash Flow sheet: categories, no merchants")).toBeVisible();
  const table = page.getByRole("table", { name: "Spending by category in January 2026" });
  await table.getByRole("button", { name: /Health/ }).click();
  await table.getByRole("button", { name: "Doctors" }).click();
  const lines = page.getByRole("region", { name: "Lines: Health / Doctors" });
  await expect(lines.getByText(/Cash Flow sheet/).first()).toBeVisible();

  await page.goto("/spending?month=2026-07");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^In July 2026 you spent/);
  const merchants = page.getByRole("list", { name: "Top merchants" });
  await expect(merchants.getByRole("listitem").first()).toBeVisible();
  await merchants.getByRole("button").first().click();
  await expect(page.getByRole("region", { name: /^Lines: / })).toBeVisible();
  await expect(page.getByRole("img", { name: /^Spending by month/ })).toBeVisible();
});
