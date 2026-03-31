import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis, mockStatus, mockRules } from "./helpers";

test.describe("Dashboard: Stitch design", () => {
  test.beforeEach(async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/");
  });

  test("renders Events Today stat card with value", async ({ page }) => {
    await expect(page.getByText("Events Today")).toBeVisible();
    await expect(page.getByText("142")).toBeVisible();
  });

  test("renders Violations stat card with accent color value", async ({ page }) => {
    await expect(page.getByText("Violations").first()).toBeVisible();
    await expect(page.getByText("3").first()).toBeVisible();
  });

  test("renders Blocked stat card", async ({ page }) => {
    await expect(page.getByText("Blocked").first()).toBeVisible();
    await expect(page.getByText("2").first()).toBeVisible();
  });

  test("renders Cost Total stat card", async ({ page }) => {
    await expect(page.getByText("Cost Total")).toBeVisible();
    await expect(page.getByText(mockStatus.cost_total)).toBeVisible();
  });

  test("renders 24h Event Timeline chart area", async ({ page }) => {
    await expect(page.getByText("24h Event Timeline")).toBeVisible();
    await expect(page.getByText("Real-time Safety Drift")).toBeVisible();
  });

  test("renders timeline chart legend items", async ({ page }) => {
    await expect(page.getByText("Safe", { exact: true })).toBeVisible();
    await expect(page.getByText("Warning", { exact: true }).first()).toBeVisible();
  });

  test("renders Live Event Feed with events", async ({ page }) => {
    await expect(page.getByText("Live Event Feed")).toBeVisible();
    await expect(page.getByText("file_write /etc/passwd")).toBeVisible();
    await expect(page.getByText("agent-alpha").first()).toBeVisible();
  });

  test("renders Top Triggered Rules table", async ({ page }) => {
    await expect(page.getByText("Top Triggered Rules")).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /rule name/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /severity/i })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: /hits/i })).toBeVisible();
  });

  test("rules table shows top rules sorted by hit count", async ({ page }) => {
    const firstRule = mockRules.sort((a, b) => b.hit_count - a.hit_count)[0];
    await expect(page.getByText(firstRule.name).first()).toBeVisible();
  });

  test("Material Symbols icons are present in stat cards", async ({ page }) => {
    const icons = page.locator(".material-symbols-outlined");
    await expect(icons.first()).toBeVisible();
    const count = await icons.count();
    expect(count).toBeGreaterThan(3);
  });

  test("displays critical violation alert banner when violations exist", async ({ page }) => {
    await expect(page.getByText("Critical Violation Detected")).toBeVisible();
    await expect(page.getByText(/3 violations? detected today/)).toBeVisible();
  });

  test("header shows System Active status badge", async ({ page }) => {
    await expect(page.getByText("System Active")).toBeVisible();
  });
});
