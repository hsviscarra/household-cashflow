import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic Diners Club statement (api/tests/fixtures/statements.py: diners_full).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-diners-full.pdf", import.meta.url));

test("read a Diners statement: matched by cardholder, ties out per card, loads", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();

  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-diners-full.pdf" });
  await expect(row).toContainText("Diners Club Hernan");
  // First run reads the lines; a re-run finds the preview or the loaded import.
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Diners Club Hernan, Jun 4, 2026 – Jul 3, 2026",
  );
  await expect(page.getByText("Ties out to the statement")).toBeVisible();
  await expect(page.getByText("Card •••• 5678 subtotal")).toBeVisible();
  await expect(page.getByText("Remaining balance of deferred purchases")).toBeVisible();
  await expect(
    page
      .getByText(/installment 8 of 12/)
      .filter({ visible: true })
      .first(),
  ).toBeAttached();

  const approve = page.getByRole("button", { name: "Approve import" });
  if (await approve.isVisible()) {
    await approve.click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  } else {
    await expect(page.getByText(/Loaded by/)).toBeVisible();
  }

  await page.goto("/transactions?month=2026-06");
  await expect(page.getByText("SUPERMAXI CUMBAYA").filter({ visible: true })).toBeVisible();
});
