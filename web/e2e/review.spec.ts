import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// The synthetic Produbanco statement leaves three merchants without a category.
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-produbanco-full.pdf", import.meta.url));

test("review: categorize a merchant once and save the rule", async ({ page }) => {
  // Make sure the statement is loaded (another spec may have done it already).
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();
  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-produbanco-full.pdf" });
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) {
    await read.click();
    await page.getByRole("button", { name: "Approve import" }).click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  } else if (await row.getByRole("link", { name: "Review" }).isVisible()) {
    await row.getByRole("link", { name: "Review" }).click();
    await page.getByRole("button", { name: "Approve import" }).click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  }

  await page.goto("/review?month=2026-07");
  await expect(page.getByRole("heading", { level: 1, name: "Review" })).toBeVisible();
  const visa = page.getByRole("listitem", { name: "DEBITO VISA" });
  if (await visa.isVisible()) {
    await visa.getByLabel("Category for DEBITO VISA").selectOption({ label: "Groceries / Supermarket" });
    await visa.getByRole("button", { name: /Categorize 1 line/ }).click();
    await expect(page.getByText(/DEBITO VISA: 1 line → Groceries \/ Supermarket\. Rule saved/)).toBeVisible();
    await expect(visa).toHaveCount(0);
  }

  await page.goto("/transactions?month=2026-07");
  await expect(page.getByText("Groceries / Supermarket").filter({ visible: true }).first()).toBeVisible();
  await page.goto("/settings?tab=rules");
  await expect(page.getByText("DEBITO VISA").filter({ visible: true }).first()).toBeVisible();
});
