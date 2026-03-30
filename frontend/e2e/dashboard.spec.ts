import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/");
  });

  test("renders stat cards with correct data", async ({ page }) => {
    await expect(page.getByText("Events Today")).toBeVisible();
    await expect(page.getByText("142")).toBeVisible();
    await expect(page.getByText("Violations", { exact: true })).toBeVisible();
    await expect(page.getByRole("paragraph").filter({ hasText: /^Blocked$/ })).toBeVisible();
    await expect(page.getByText("$48.23")).toBeVisible();
  });

  test("renders violation alert banner", async ({ page }) => {
    await expect(
      page.getByText(/violation.*detected today/i),
    ).toBeVisible();
  });

  test("renders 24h event timeline chart area", async ({ page }) => {
    await expect(page.getByText("24h Event Timeline")).toBeVisible();
    // Legend items
    await expect(page.getByText("Safe", { exact: true })).toBeVisible();
    await expect(page.getByText("Warning", { exact: true })).toBeVisible();
  });

  test("renders live event feed with events", async ({ page }) => {
    await expect(page.getByText("Live Event Feed")).toBeVisible();
    await expect(page.getByText("file_write /etc/passwd")).toBeVisible();
    await expect(page.getByText("agent-alpha")).toBeVisible();
  });

  test("renders top triggered rules table", async ({ page }) => {
    await expect(page.getByText("Top Triggered Rules")).toBeVisible();
    await expect(page.getByText("System File Protection", { exact: true })).toBeVisible();
    await expect(page.getByText("87")).toBeVisible();
  });
});
