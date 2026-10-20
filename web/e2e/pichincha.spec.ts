import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic Banco Pichincha statement (api/tests/fixtures/statements.py: pichincha_full).
const SAMPLE = fileURLToPath(new URL("./fixtures/sample-pichincha-full.pdf", import.meta.url));

test("read a Banco Pichincha statement: ties out and loads", async ({ page }) => {
  await page.goto("/import");
  await page.getByLabel("Statement PDFs").setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Upload statements" }).click();
  await expect(page.getByText(/of 1 saved\./)).toBeVisible();

  const row = page
    .getByRole("table", { name: "Uploaded statements" })
    .getByRole("row")
    .filter({ hasText: "sample-pichincha-full.pdf" });
  // First run reads the lines; a re-run finds the preview or the loaded import.
  const read = row.getByRole("button", { name: /Read lines/ });
  if (await read.isVisible()) await read.click();
  else await row.getByRole("link", { name: /Review|View/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Pichincha Mastercard Black, Jun 13, 2026 – Jul 12, 2026",
  );
  await expect(page.getByText("Ties out to the statement")).toBeVisible();
  await expect(page.getByText("Card •••• 6331 subtotal")).toBeVisible();
  await expect(
    page
      .getByText(/installment 2 of 6/)
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

  await page.goto("/transactions?month=2026-07");
  await expect(page.getByText("CONECEL VARIOS UIO").filter({ visible: true })).toBeVisible();
  await expect(page.getByText("Utilities / Phone/Internet").filter({ visible: true })).toBeVisible();
});
