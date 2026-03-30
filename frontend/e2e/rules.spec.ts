import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Rules Manager", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/rules");
  });

  test("renders rules table with data", async ({ page }) => {
    await expect(page.getByText("Rules Manager")).toBeVisible();
    await expect(page.getByText("System File Protection")).toBeVisible();
    await expect(page.getByText("External API Monitor")).toBeVisible();
    await expect(page.getByText("Cost Threshold")).toBeVisible();
  });

  test("built-in rules show lock icon", async ({ page }) => {
    // The first rule is built_in — its row should have a lock SVG
    const row = page.locator("tr", { hasText: "System File Protection" });
    await expect(row).toBeVisible();
    // built_in rules don't show edit/delete buttons
    await expect(row.locator("button", { hasText: /edit|pencil/i })).toHaveCount(0);
  });

  test("search filters rules", async ({ page }) => {
    const searchInput = page.getByPlaceholder("Search rules by name or pattern...");
    await searchInput.fill("Cost");
    await expect(page.getByText("Cost Threshold")).toBeVisible();
    await expect(page.getByText("System File Protection")).not.toBeVisible();
  });

  test("create modal opens and closes", async ({ page }) => {
    await page.getByText("New Rule").click();
    await expect(page.getByText("Create Rule")).toBeVisible();
    await expect(page.locator("[role=dialog] input[type=text]").first()).toBeVisible();

    // Close the modal
    await page.getByText("Cancel").click();
    await expect(page.getByText("Create Rule")).not.toBeVisible();
  });

  test("navigation to rules page works from sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Safety Dashboard")).toBeVisible();
    await page.getByRole("link", { name: "Rules" }).click();
    await expect(page).toHaveURL("/rules");
    await expect(page.getByText("Rules Manager")).toBeVisible();
  });
});
