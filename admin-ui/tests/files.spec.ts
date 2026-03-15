import { test, expect } from "@playwright/test";

test.describe("Files Page", () => {
  test("table renders with column headers", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".page-title")).toHaveText("FILES");

    // Table headers should be visible
    await expect(page.locator("th:has-text('Filename')")).toBeVisible();
    await expect(page.locator("th:has-text('Category')")).toBeVisible();
    await expect(page.locator("th:has-text('Size')")).toBeVisible();
    await expect(page.locator("th:has-text('Description')")).toBeVisible();
  });

  test("search input and button are present", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".term-input")).toBeVisible();
    await expect(page.locator("text=[ SEARCH ]")).toBeVisible();
  });

  test("category dropdown is present", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".term-select").first()).toBeVisible();
  });

  test("pagination controls are present", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=[ PREV ]")).toBeVisible();
    await expect(page.locator("text=[ NEXT ]")).toBeVisible();
  });
});
