import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Auth: unauthenticated access", () => {
  test("redirects to /login when no token is present", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page shows BSupervisor branding", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "BSupervisor" })).toBeVisible();
    await expect(page.getByText("Monitor, audit, and secure your AI agents")).toBeVisible();
  });

  test("login page shows feature highlights", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Behavior Logging")).toBeVisible();
    await expect(page.getByText("Risk Detection")).toBeVisible();
    await expect(page.getByText("Daily Reports")).toBeVisible();
  });

  test("sign in button redirects to auth.bsvibe.dev", async ({ page }) => {
    await page.goto("/login");
    const [request] = await Promise.all([
      page.waitForRequest((req) => req.url().includes("auth.bsvibe.dev")),
      page.getByRole("button", { name: /sign in with bsvibe/i }).click(),
    ]);
    expect(request.url()).toContain("auth.bsvibe.dev/login");
    expect(request.url()).toContain("redirect_uri=");
  });

  test("login page shows Powered by BSVibe footer", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Powered by BSVibe")).toBeVisible();
  });

  test("authenticated user can access dashboard without redirect", async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/");
    await expect(page).toHaveURL("/");
    await expect(page.getByText("Safety Dashboard")).toBeVisible();
  });
});
