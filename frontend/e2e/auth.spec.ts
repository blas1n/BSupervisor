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

  test("sign in button navigates to auth.bsvibe.dev/login", async ({ page }) => {
    await page.goto("/login");
    // Intercept the cross-origin navigation triggered by window.location.href
    await page.route("**/auth.bsvibe.dev/**", (route) => route.abort());
    const requestPromise = page.waitForRequest((req) =>
      req.url().includes("auth.bsvibe.dev/login"),
    );
    await page.getByRole("button", { name: /sign in with bsvibe/i }).click();
    const request = await requestPromise;
    expect(request.url()).toContain("auth.bsvibe.dev/login");
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
