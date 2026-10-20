import { expect, test } from "@playwright/test";

// Runs against the real API and database seeded by migration 0003.

test("accounts show the seeded cards with the last four digits only", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText("Capital One Venture")).toBeVisible();
  await expect(page.getByText("•••• 4003")).toBeVisible();
  await expect(page.getByText("Database connected")).toBeVisible();
});

test("categories are grouped by what they count as", async ({ page }) => {
  await page.goto("/settings?tab=categories");
  await expect(page.getByRole("heading", { name: "Expenses" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Income" })).toBeVisible();
  await expect(page.getByText("Food Delivery")).toBeVisible();
});

test("a new merchant rule categorizes a description, then is removed", async ({ page }, testInfo) => {
  const pattern = `E2E SHOP ${testInfo.project.name.toUpperCase()} ${Date.now()}`;
  await page.goto("/settings");
  await page.getByRole("tab", { name: "Merchant rules" }).click();
  await expect(page).toHaveURL(/tab=rules/);

  const tester = page.getByLabel("Try a statement description");
  await tester.fill("UBER EATS SAN JOSE");
  await page.getByRole("button", { name: "Test rules" }).click();
  await expect(page.locator("strong", { hasText: "Dining / Food Delivery" })).toBeVisible();

  await page.getByRole("button", { name: "Add rule" }).click();
  await page.getByLabel("Pattern in the statement description").fill(pattern);
  await page.getByLabel("Category").selectOption({ label: "Travel" });
  await page.getByLabel("Priority (lower runs first)").fill("5");
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByText(`Rule added: ${pattern} → Travel.`)).toBeVisible();

  await tester.fill(`pos ${pattern.toLowerCase()} quito`);
  await page.getByRole("button", { name: "Test rules" }).click();
  await expect(page.locator("strong", { hasText: "Travel" })).toBeVisible();

  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: `Delete rule ${pattern}` }).click();
  await expect(page.getByText(`Rule deleted: ${pattern}.`)).toBeVisible();
  await expect(page.getByRole("cell", { name: pattern })).toHaveCount(0);
});
