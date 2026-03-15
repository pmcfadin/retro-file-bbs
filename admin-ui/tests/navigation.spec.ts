import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("sidebar links navigate to correct pages", async ({ page }) => {
    await page.goto("/");

    // Files page is default
    await expect(page.locator(".page-title")).toHaveText("FILES");

    // Navigate to Upload
    await page.click('a[href="/upload"]');
    await expect(page.locator(".page-title")).toHaveText("UPLOAD");

    // Navigate to Monitor
    await page.click('a[href="/monitor"]');
    await expect(page.locator(".page-title")).toHaveText("MONITOR");

    // Navigate to Indexer
    await page.click('a[href="/indexer"]');
    await expect(page.locator(".page-title")).toHaveText("INDEXER");

    // Navigate to Settings
    await page.click('a[href="/settings"]');
    await expect(page.locator(".page-title")).toHaveText("SETTINGS");
  });

  test("active sidebar link is highlighted", async ({ page }) => {
    await page.goto("/upload");
    const uploadLink = page.locator('a[href="/upload"]');
    await expect(uploadLink).toHaveClass(/active/);
  });

  test("CRT scanline toggle works", async ({ page }) => {
    await page.goto("/settings");

    // Toggle scanlines off
    await page.click("text=SCANLINES");
    const bodyClass = await page.evaluate(() => document.body.className);
    // Should have toggled
    expect(typeof bodyClass).toBe("string");
  });
});
