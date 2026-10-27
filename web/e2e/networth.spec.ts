import { expect, test } from "@playwright/test";

// Runs after the workbook spec: the synthetic sheet's BIESS balance is a loan on the balance
// sheet. Adds a vehicle (once) and checks it counts.
test("balance sheet: the workbook's loan, a vehicle added on the page, net worth", async ({ page }) => {
  await page.goto("/debt");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Net worth −?[\d,]+\.\d{2}: you own/);
  const owe = page.getByRole("region", { name: "What you owe" });
  await expect(owe.getByRole("listitem", { name: "BIESS" })).toContainText("30,000.55");

  const own = page.getByRole("region", { name: "What you own" });
  if (!(await own.getByRole("listitem", { name: "Sample car" }).isVisible())) {
    await page.getByRole("button", { name: "Add something you own or owe" }).click();
    const form = page.getByRole("form", { name: "Add something you own or owe" });
    await form.getByLabel("Name").fill("Sample car");
    await form.getByLabel("What it is").selectOption("vehicle");
    await form.getByLabel("Value", { exact: true }).fill("12000");
    await form.getByLabel("Value on").fill("2025-06-01");
    await form.getByRole("button", { name: "Add" }).click();
    await expect(page.getByText("Sample car added.")).toBeVisible();
  }
  const car = own.getByRole("listitem", { name: "Sample car" });
  await expect(car).toContainText(/1[12],[05]00\.00/); // re-valued by an earlier run
  await car.getByRole("button", { name: "Update value" }).click();
  const value = car.getByRole("form", { name: "New value for Sample car" });
  await value.getByLabel("Value").fill("11500");
  await value.getByRole("button", { name: "Save value" }).click();
  await expect(car).toContainText("11,500.00");
  await expect(page.getByRole("img", { name: /^Net worth by month/ })).toBeVisible();
});
