import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Navigation: Stitch sidebar", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
  });

  test("sidebar shows BSupervisor logo and Safety Platform label", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("BSupervisor").first()).toBeVisible();
    await expect(page.getByText("Safety Platform")).toBeVisible();
  });

  test("sidebar shows Monitor section label", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Monitor", { exact: true })).toBeVisible();
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
    await expect(dashLink).toHaveClass(/text-accent/);
  });

  test("clicking Rules navigates to /rules with active state", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /rules/i }).click();
    await expect(page).toHaveURL("/rules");
    await expect(page.getByRole("link", { name: /rules/i })).toHaveClass(/text-accent/);
    await expect(page.getByText("Rules Manager")).toBeVisible();
  });

  test("clicking Reports navigates to /reports", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /reports/i }).click();
    await expect(page).toHaveURL("/reports");
    await expect(page.getByText("Daily Report")).toBeVisible();
  });

  test("clicking Costs navigates to /costs", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /costs/i }).click();
    await expect(page).toHaveURL("/costs");
    await expect(page.getByText("Cost Monitor")).toBeVisible();
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
    // At least logo shield + 4 nav icons + chevron + person + logout = 8+
    expect(count).toBeGreaterThanOrEqual(7);
  });

  test("active nav item shows chevron_right indicator", async ({ page }) => {
    await page.goto("/");
    const dashLink = page.getByRole("link", { name: /dashboard/i });
    await expect(
      dashLink.locator(".material-symbols-outlined").filter({ hasText: "chevron_right" }),
    ).toBeVisible();
  });
});
