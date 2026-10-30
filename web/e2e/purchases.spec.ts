import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

// A synthetic SRI invoice (api/tests/fixtures/invoices.py: factura): 4 products, 15.98, Oct 28 2026.
const XML = fileURLToPath(new URL("./fixtures/sample-invoice.xml", import.meta.url));

test("purchases: an invoice XML becomes products by group, and a product gets its group", async ({
  page,
}) => {
  await page.goto("/purchases?month=2026-10");
  await page.getByLabel("Invoice XML files").setInputFiles(XML);
  const results = page.getByRole("list", { name: "Upload results" });
  await expect(results).toContainText(/Added|Already here/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("What you bought in October 2026");

  const groups = page.getByRole("region", { name: "By product group" });
  await expect(groups).toContainText("Household & Cleaning");

  // The phone run comes after the desktop one: by then the yogurt already has its group.
  const todo = page.getByRole("region", { name: "Products to group" });
  const choose = todo.getByLabel("Group for YOG TONI FRUT 1L");
  if (await choose.count()) {
    await choose.selectOption("Dairy & Eggs");
    await todo
      .locator("li", { hasText: "YOG TONI FRUT 1L" })
      .getByRole("button", { name: "Save group" })
      .click();
    await expect(page.getByText("YOG TONI FRUT 1L: saved as Dairy & Eggs.")).toBeVisible();
  }

  const list = page.getByRole("region", { name: "Invoices" });
  await list.getByRole("button", { name: /SUPER PRUEBA/ }).click();
  const products = list.getByRole("table");
  await expect(products).toContainText("DETERGENTE POLVO 2KG");
  await expect(products.getByRole("row", { name: /YOG TONI FRUT 1L/ })).toContainText("Dairy & Eggs");
});
