import { test, expect } from "@playwright/test";

test.describe("Monitor Page", () => {
  test("sessions table renders", async ({ page }) => {
    await page.goto("/monitor");
    await expect(page.locator(".page-title")).toHaveText("MONITOR");

    // Session table headers
    await expect(page.locator("th:has-text('Session')").first()).toBeVisible();
    await expect(page.locator("th:has-text('IP')").first()).toBeVisible();
    await expect(page.locator("th:has-text('State')")).toBeVisible();
  });

  test("log viewer is present", async ({ page }) => {
    await page.goto("/monitor");
    await expect(page.locator(".log-viewer")).toBeVisible();
  });

  test("pause/resume button works", async ({ page }) => {
    await page.goto("/monitor");
    const btn = page.locator("text=[ PAUSE ]");
    await expect(btn).toBeVisible();
    await btn.click();
    await expect(page.locator("text=[ RESUME ]")).toBeVisible();
  });
});
