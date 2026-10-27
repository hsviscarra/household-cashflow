import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// The synthetic Capital One statement charges 10.00 interest on purchases (statements.py).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-capitalone-full.pdf", import.meta.url));

test("debt and subscriptions: Capital One's interest this year, the subscriptions page", async ({ page }) => {
  // Make sure the statement is loaded (the Capital One spec may have done it already).
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();
  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-capitalone-full.pdf" });
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  const approve = page.getByRole("button", { name: "Approve import" });
  await expect(approve.or(page.getByText(/Loaded by/)).first()).toBeVisible();
  if (await approve.isVisible()) {
    await approve.click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  }

  await page.goto("/debt?year=2026");
  await expect(
    page.getByRole("heading", { level: 2, name: /^2026( so far)?: [\d,]+\.\d{2} in interest/ }),
  ).toBeVisible();
  const table = page.getByRole("table", { name: "Interest and fees by account, 2026" });
  const co = table.getByRole("row", { name: /Capital One Venture/ });
  await expect(co).toContainText("10.00");
  await co.getByRole("button").click();
  await expect(page.getByRole("list", { name: "Capital One Venture: 2026 by kind" })).toContainText(
    "Credit Card Interest",
  );

  await page.goto("/subscriptions");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Looking for repeating charges…")).toHaveCount(0);
});
