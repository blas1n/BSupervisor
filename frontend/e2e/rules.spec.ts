import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Rules Manager: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/rules");
  });

  test("renders page header with Audit Rules Management title", async ({ page }) => {
    await expect(page.getByText("Audit Rules Management")).toBeVisible();
    await expect(page.getByText("Configure safety triggers and thresholds")).toBeVisible();
  });

  test("renders rules table with all column headers", async ({ page }) => {
    await expect(page.getByRole("columnheader", { name: /name/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /type/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /pattern/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /severity/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /action/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /status/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /hits/i })).toBeVisible();
  });

  test("displays all mock rules in the table", async ({ page }) => {
    await expect(page.getByText("System File Protection")).toBeVisible();
    await expect(page.getByText("External API Monitor")).toBeVisible();
    await expect(page.getByText("Cost Threshold")).toBeVisible();
  });

  test("Create Rule button is visible", async ({ page }) => {
    await expect(page.getByRole("button", { name: /create rule/i })).toBeVisible();
  });

  test("search bar is present and accepts input", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search rules/i);
    await expect(searchInput).toBeVisible();
    await searchInput.fill("System");
    await expect(page.getByText("System File Protection")).toBeVisible();
    await expect(page.getByText("External API Monitor")).not.toBeVisible();
  });

  test("clicking Create Rule opens Create Rule modal", async ({ page }) => {
    await page.getByRole("button", { name: /create rule/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Create Rule" })).toBeVisible();
  });

  test("modal has form fields for name, type, severity, action, pattern, description", async ({ page }) => {
    await page.getByRole("button", { name: /create rule/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.locator("label").filter({ hasText: "Name" })).toBeVisible();
    await expect(dialog.locator("label").filter({ hasText: "Type" })).toBeVisible();
    await expect(dialog.locator("label").filter({ hasText: "Severity" })).toBeVisible();
    await expect(dialog.locator("label").filter({ hasText: "Action" })).toBeVisible();
    await expect(dialog.locator("label").filter({ hasText: "Pattern" })).toBeVisible();
    await expect(dialog.locator("label").filter({ hasText: "Description" })).toBeVisible();
  });

  test("modal can be closed with Cancel button", async ({ page }) => {
    await page.getByRole("button", { name: /create rule/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible();
  });

  test("built-in rules show lock icon", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "System File Protection" });
    await expect(row.locator(".material-symbols-outlined").filter({ hasText: "lock" })).toBeVisible();
  });

  test("non-built-in rules show edit and delete buttons", async ({ page }) => {
    const row = page.getByRole("row").filter({ hasText: "External API Monitor" });
    await expect(row.locator(".material-symbols-outlined").filter({ hasText: "edit" })).toBeVisible();
    await expect(row.locator(".material-symbols-outlined").filter({ hasText: "delete" })).toBeVisible();
  });

  test("type filter dropdown is visible", async ({ page }) => {
    const select = page.locator("select");
    await expect(select).toBeVisible();
    await expect(select).toHaveValue("all");
  });
});
