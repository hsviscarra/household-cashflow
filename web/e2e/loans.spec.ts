import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// Synthetic lender table (api/tests/fixtures/statements.py: loan_table): 12 installments from
// January 2026, 10 paid, balance 2,000.00 after October.
const TABLE = fileURLToPath(new URL("./fixtures/sample-loan-table.pdf", import.meta.url));

test("loan: upload the amortization table, see the balance, summary and payments", async ({ page }) => {
  await page.goto("/debt");
  const owe = page.getByRole("region", { name: "What you owe" });
  await expect(owe.getByRole("listitem", { name: "BIESS" })).toBeVisible();
  if (!(await owe.getByRole("listitem", { name: "Sample mortgage" }).isVisible())) {
    await page.getByRole("button", { name: "Add something you own or owe" }).click();
    const form = page.getByRole("form", { name: "Add something you own or owe" });
    await form.getByLabel("Name").fill("Sample mortgage");
    await form.getByLabel("What it is").selectOption("loan");
    await form.getByLabel("Value", { exact: true }).fill("12000");
    await form.getByLabel("Value on").fill("2025-12-31");
    await form.getByRole("button", { name: "Add" }).click();
    await expect(page.getByText("Sample mortgage added.")).toBeVisible();
  }
  const loan = owe.getByRole("listitem", { name: "Sample mortgage" });
  await loan.getByLabel("Amortization table for Sample mortgage").setInputFiles(TABLE);
  await expect(page.getByText("Read 12 installments: 10 paid, 2 to go; balance 2,000.00.")).toBeVisible();
  await expect(loan).toContainText("2,000.00");
  await expect(loan).toContainText("10 of 12 installments paid · next 1,022.50 in November 2026");
  await loan.getByRole("button", { name: "Payments" }).click();
  const payments = loan.getByRole("list", { name: "Payments for Sample mortgage" });
  await expect(payments.getByRole("listitem")).toHaveCount(12);
  await expect(payments.getByRole("listitem").last()).toContainText("Due");
});
