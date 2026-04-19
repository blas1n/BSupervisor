import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Settings page: generic integrations", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/settings") && r.request().method() === "GET"),
      page.goto("/settings"),
    ]);
  });

  test("renders page header with Settings title", async ({ page }) => {
    await expect(page.getByText("Settings").first()).toBeVisible();
    await expect(
      page.getByText("Configure connections to external services"),
    ).toBeVisible();
  });

  test("renders Agent Platforms section", async ({ page }) => {
    await expect(page.getByText("Agent Platforms")).toBeVisible();
  });

  test("loads saved integrations from API", async ({ page }) => {
    // Two integrations from mock data — name fields have the values
    const nameInputs = page.locator('input[placeholder="My Agent Platform"]');
    await expect(nameInputs).toHaveCount(2);
    await expect(nameInputs.nth(0)).toHaveValue("BSNexus");
    await expect(nameInputs.nth(1)).toHaveValue("BSGateway");
  });

  test("renders notification channels card", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Notification Channels" })).toBeVisible();
    await expect(page.getByPlaceholder("123456:ABC-DEF...")).toBeVisible();
    await expect(
      page.getByPlaceholder("https://hooks.slack.com/services/..."),
    ).toBeVisible();
  });

  test("Add Integration button is visible", async ({ page }) => {
    await expect(page.getByTestId("add-integration")).toBeVisible();
  });

  test("clicking Add Integration adds a new card", async ({ page }) => {
    const initialCards = await page.getByTestId("remove-integration").count();
    await page.getByTestId("add-integration").click();
    await expect(page.getByTestId("remove-integration")).toHaveCount(initialCards + 1);
    await expect(page.getByText("New Integration")).toBeVisible();
  });

  test("Remove button removes an integration card", async ({ page }) => {
    const initialCount = await page.getByTestId("remove-integration").count();
    await page.getByTestId("remove-integration").first().click();
    await expect(page.getByTestId("remove-integration")).toHaveCount(initialCount - 1);
  });

  test("Save Settings button is visible", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /save settings/i }),
    ).toBeVisible();
  });

  test("clicking Save Settings shows success message", async ({ page }) => {
    await page.getByRole("button", { name: /save settings/i }).click();
    await expect(page.getByText("Settings saved")).toBeVisible();
  });

  test("Test buttons are visible for each integration", async ({ page }) => {
    // One test button per integration that has an endpoint URL
    const testButtons = page.getByRole("button", { name: /test/i });
    await expect(testButtons).toHaveCount(2);
  });

  test("integration type dropdown has all options", async ({ page }) => {
    const select = page.locator("select").first();
    const options = select.locator("option");
    await expect(options).toHaveCount(6);
  });

  test("settings link is in the sidebar", async ({ page }) => {
    const settingsLink = page.locator("nav a").filter({ hasText: "Settings" });
    await expect(settingsLink).toBeVisible();
  });
});
