import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic Pacificard statement: a PDF holding a screenshot (api/tests/fixtures/statements.py).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-pacificard-full.pdf", import.meta.url));

test("read a Pacificard screenshot with OCR: ties out and loads", async ({ page }) => {
  test.setTimeout(240_000); // OCR takes tens of seconds
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible({ timeout: 60_000 });

  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-pacificard-full.pdf" });
  await expect(row).toContainText("Pacificard Mastercard Black");
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Pacificard Mastercard Black, Aug 25, 2026 – Sep 24, 2026",
    { timeout: 180_000 },
  );
  await expect(page.getByText("Ties out to the statement")).toBeVisible();

  const approve = page.getByRole("button", { name: "Approve import" });
  if (await approve.isVisible()) {
    await approve.click();
    await expect(page.getByText("Import approved.")).toBeVisible();
  } else {
    await expect(page.getByText(/Loaded by/)).toBeVisible();
  }
  await page.goto("/transactions?month=2026-09");
  await expect(page.getByText("SUPERMAXI CUMBAYA QUITO").filter({ visible: true })).toBeVisible();
});
