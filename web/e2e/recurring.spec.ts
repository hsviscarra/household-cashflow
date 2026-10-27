import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// The synthetic workbook (api/tests/fixtures/workbook.py) has 2026 values in January and a plan
// for July: its rows become recurring templates and the grid shows the sheet's numbers.
const SAMPLE = fileURLToPath(new URL("./fixtures/cash-flow-sample.xlsx", import.meta.url));

test("recurring: the sheet's rows become templates and the grid reproduces them", async ({ page }) => {
  // Make sure the workbook is loaded (the history spec may have done it already).
  await page.goto("/import");
  await page.getByLabel("Workbook (.xlsx)").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText(/5 months/)).toBeVisible();
  const load = page.getByRole("button", { name: "Load history" });
  if (await load.isEnabled()) {
    await load.click();
    await expect(page.getByText("History loaded.")).toBeVisible();
  }

  await page.goto("/recurring?year=2026");
  const table = page.getByRole("table", { name: "Recurring items in 2026, by month" });
  const choose = page.getByRole("button", { name: "Choose rows from the 2026 sheet" });
  await expect(table.or(choose)).toBeVisible();
  if (await choose.isVisible()) {
    await choose.click();
    const picker = page.getByRole("region", { name: "Rows of the 2026 sheet" });
    await expect(picker.getByRole("checkbox", { name: /Hernan \(Salaries\)/ })).toBeChecked();
    await picker.getByRole("button", { name: /^Create \d+ templates$/ }).click();
    await expect(page.getByText(/templates created; 2026 filled with/)).toBeVisible();
  }

  // January comes from the sheet (paid), July from its plan (expected).
  await expect(
    table.getByRole("button", { name: "Hernan (Salaries), January 2026: 4,900.25, paid" }),
  ).toBeVisible();
  await expect(
    table.getByRole("button", { name: "Hernan (Salaries), July 2026: 4,900.00, expected" }),
  ).toBeVisible();

  // A cell's details.
  await table.getByRole("button", { name: "Hernan (Salaries), January 2026: 4,900.25, paid" }).click();
  const panel = page.getByRole("region", { name: "Hernan (Salaries) in January 2026" });
  await expect(panel.getByRole("heading", { name: "Lines that paid it" })).toBeVisible();
  await expect(panel.getByText("Cash Flow sheet").first()).toBeVisible();
});
