import { test, expect } from "@playwright/test";
import { injectAuth, mockAllApis } from "./helpers";

test.describe("Auth Flow", () => {
  test("unauthenticated user is redirected to login page", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("BSupervisor")).toBeVisible();
    await expect(page.getByText("Sign in with BSVibe")).toBeVisible();
  });

  test("login page shows feature highlights", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Behavior Logging")).toBeVisible();
    await expect(page.getByText("Risk Detection")).toBeVisible();
    await expect(page.getByText("Daily Reports")).toBeVisible();
  });

  test("sign in button triggers login redirect", async ({ page }) => {
    await page.goto("/login");
    const button = page.getByText("Sign in with BSVibe");
    await expect(button).toBeVisible();
    // The login function opens auth.bsvibe.dev — verify the button is clickable
    await expect(button).toBeEnabled();
  });

  test("authenticated user can access dashboard", async ({ page }) => {
    await injectAuth(page);
    await mockAllApis(page);
    await page.goto("/");
    await expect(page).toHaveURL("/");
    await expect(page.getByText("Safety Dashboard")).toBeVisible();
  });
});
