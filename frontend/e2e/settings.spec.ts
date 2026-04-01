import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Settings page: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/settings");
  });

  test("renders page header with Settings title", async ({ page }) => {
    await expect(page.getByText("Settings").first()).toBeVisible();
    await expect(
      page.getByText("Configure connections to external services"),
    ).toBeVisible();
  });

  test("renders BSNexus connection card", async ({ page }) => {
    await expect(page.getByText("BSNexus Connection")).toBeVisible();
    await expect(page.getByPlaceholder("https://nexus.bsvibe.dev")).toBeVisible();
  });

  test("renders BSGateway connection card", async ({ page }) => {
    await expect(page.getByText("BSGateway Connection")).toBeVisible();
    await expect(page.getByPlaceholder("https://gateway.bsvibe.dev")).toBeVisible();
  });

  test("renders BSage connection card", async ({ page }) => {
    await expect(page.getByText("BSage Connection")).toBeVisible();
    await expect(page.getByPlaceholder("https://sage.bsvibe.dev")).toBeVisible();
  });

  test("renders notification channels card", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Notification Channels" })).toBeVisible();
    await expect(page.getByPlaceholder("123456:ABC-DEF...")).toBeVisible();
    await expect(
      page.getByPlaceholder("https://hooks.slack.com/services/..."),
    ).toBeVisible();
  });

  test("loads saved settings from API", async ({ page }) => {
    const nexusUrlInput = page.getByPlaceholder("https://nexus.bsvibe.dev");
    await expect(nexusUrlInput).toHaveValue("https://nexus.bsvibe.dev");

    const gatewayUrlInput = page.getByPlaceholder("https://gateway.bsvibe.dev");
    await expect(gatewayUrlInput).toHaveValue("https://gateway.bsvibe.dev");
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

  test("Test buttons are visible for each connection", async ({ page }) => {
    const testButtons = page.getByRole("button", { name: /test/i });
    await expect(testButtons).toHaveCount(3);
  });

  test("settings link is in the sidebar", async ({ page }) => {
    const settingsLink = page.locator("nav a").filter({ hasText: "Settings" });
    await expect(settingsLink).toBeVisible();
  });
});
