import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Loads the synthetic sample workbook (api/tests/fixtures/workbook.py) through the Import page,
// then reads the Overview. The second project finds it already loaded and goes straight on.
const SAMPLE = fileURLToPath(new URL("./fixtures/cash-flow-sample.xlsx", import.meta.url));

test("load the Excel history, then see it on the Overview", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Workbook (.xlsx)").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText(/5 months/)).toBeVisible();
  await page.getByText(/months where the workbook’s TOTAL differs/).click();
  await expect(page.getByText(/left out Aliquota Ofi 75.35/)).toBeVisible();

  const loadButton = page.getByRole("button", { name: "Load history" });
  if (await loadButton.isEnabled()) {
    await loadButton.click();
    await expect(page.getByText("History loaded.")).toBeVisible();
    await page.getByRole("link", { name: "See the Overview" }).click();
  } else {
    await expect(page.getByText("This exact file is already loaded.")).toBeVisible();
    await page.goto("/");
  }

  // Other tests may add statement months to 2026, so check the years that only the workbook fills.
  await expect(page.getByRole("heading", { level: 1 })).toContainText("2026 you");
  await expect(page.getByRole("img", { name: "Money in and out by month, 2026" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Salary" })).toBeVisible();

  await page.getByRole("button", { name: "2019" }).click();
  await expect(page).toHaveURL(/year=2019/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Nov–Dec 2019");
});
