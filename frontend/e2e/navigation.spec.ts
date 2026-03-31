import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Navigation: Stitch sidebar", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("sidebar shows BSupervisor logo and platform label", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("BSupervisor").first()).toBeVisible();
    await expect(page.getByText("AI Safety Platform")).toBeVisible();
  });

  test("sidebar has Dashboard, Rules, Reports, Costs links", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: /dashboard/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /rules/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /reports/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /costs/i })).toBeVisible();
  });

  test("Dashboard link is active on / route", async ({ page }) => {
    await page.goto("/");
    const dashLink = page.getByRole("link", { name: /dashboard/i });
    await expect(dashLink).toHaveClass(/text-gray-50/);
  });

  test("active nav item has left border accent", async ({ page }) => {
    await page.goto("/");
    const dashLink = page.getByRole("link", { name: /dashboard/i });
    await expect(dashLink).toHaveClass(/border-accent/);
  });

  test("clicking Rules navigates to /rules with active state", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /rules/i }).click();
    await expect(page).toHaveURL("/rules");
    await expect(page.getByRole("link", { name: /rules/i })).toHaveClass(/text-gray-50/);
  });

  test("clicking Reports navigates to /reports", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /reports/i }).click();
    await expect(page).toHaveURL("/reports");
  });

  test("clicking Costs navigates to /costs", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /costs/i }).click();
    await expect(page).toHaveURL("/costs");
  });

  test("sidebar shows user info when authenticated", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Test User")).toBeVisible();
    await expect(page.getByText("test@example.com")).toBeVisible();
  });

  test("sidebar shows Sign out button", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /sign out/i })).toBeVisible();
  });

  test("Sign out clears auth and redirects to login", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("navigation icons use Material Symbols Outlined", async ({ page }) => {
    await page.goto("/");
    const sidebarIcons = page.locator("aside .material-symbols-outlined");
    const count = await sidebarIcons.count();
    // Logo security icon + 4 nav icons + person + logout = 7+
    expect(count).toBeGreaterThanOrEqual(6);
  });
});
