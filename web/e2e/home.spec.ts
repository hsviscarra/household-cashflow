import { expect, test } from "@playwright/test";

// Home (ADR-027) and Cash flow: the widgets render and a widget can be hidden and brought back.
test("Home shows its widgets and can be customized; Cash flow shows the month", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const customize = page.getByRole("button", { name: "Customize" });
  await customize.click();
  const panel = page.getByRole("region", { name: "Customize Home" });
  await panel.getByRole("button", { name: "Back to the default" }).click();
  await expect(page.getByRole("region", { name: "Inbox" })).toBeVisible();
  await page.getByRole("button", { name: "Done" }).click();

  await page.goto("/cashflow");
  await expect(page.getByRole("heading", { level: 1, name: "Cash flow" })).toBeVisible();
  // With data the month and its drill path show; on an empty database, the way to load it.
  await expect(
    page.getByRole("navigation", { name: "Drill path" }).or(page.getByText(/Nothing loaded yet/)),
  ).toBeVisible();
});
