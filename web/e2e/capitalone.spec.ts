import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic Capital One statement (api/tests/fixtures/statements.py: capitalone_full).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-capitalone-full.pdf", import.meta.url));

test("read a Capital One statement, check the tie-out, approve, see the lines", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();

  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-capitalone-full.pdf" });
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) {
    await read.click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Capital One Venture, Sep 4, 2026 – Oct 3, 2026",
    );
    await expect(page.getByText("Ties out to the statement")).toBeVisible();
    await expect(page.getByText(/11 new lines/)).toBeVisible();
    await page.getByRole("button", { name: "Approve import" }).click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  } else {
    await expect(row.getByText("Loaded")).toBeVisible();
    await row.getByRole("link", { name: "View" }).click();
    await expect(page.getByText(/Loaded by/)).toBeVisible();
  }

  await page.goto("/transactions?month=2026-09");
  // A table on desktop, a list on phones: check whichever is shown.
  await expect(page.getByText("SUPERMAXI EL JARDIN QUITO").filter({ visible: true })).toBeVisible();
  await expect(page.getByText("Groceries / Supermarket").filter({ visible: true })).toBeVisible();
});
