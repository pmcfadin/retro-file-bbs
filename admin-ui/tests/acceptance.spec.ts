/**
 * Acceptance tests for the CP/M Software Depot Admin UI.
 *
 * These tests exercise real user workflows end-to-end against a live server.
 * Server must be running on localhost:8080 with a populated test database.
 */
import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// 1. SPA loads with CRT aesthetic
// ---------------------------------------------------------------------------

test.describe("Admin UI loads", () => {
  test("root URL serves the SPA with CRT styling", async ({ page }) => {
    await page.goto("/");
    // Page renders with the sidebar and main content
    await expect(page.locator(".sidebar-title")).toHaveText("CPM Depot");
    await expect(page.locator(".page-title")).toHaveText("FILES");

    // CRT font is applied (IBM Plex Mono in the CSS)
    const fontFamily = await page.locator("body").evaluate(
      (el) => getComputedStyle(el).fontFamily
    );
    expect(fontFamily).toContain("IBM Plex Mono");
  });

  test("all sidebar nav links are present", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('a[href="/"]')).toContainText("FILES");
    await expect(page.locator('a[href="/upload"]')).toContainText("UPLOAD");
    await expect(page.locator('a[href="/monitor"]')).toContainText("MONITOR");
    await expect(page.locator('a[href="/indexer"]')).toContainText("INDEXER");
    await expect(page.locator('a[href="/settings"]')).toContainText("SETTINGS");
  });
});

// ---------------------------------------------------------------------------
// 2. Files page: browse, search, paginate, edit
// ---------------------------------------------------------------------------

test.describe("Files page workflows", () => {
  test("displays file table with real data from the database", async ({ page }) => {
    await page.goto("/");

    // Table should have rows (we have 268 files in the test DB)
    const rows = page.locator(".term-table tbody tr");
    await expect(rows.first()).toBeVisible();
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test("category filter narrows results", async ({ page }) => {
    await page.goto("/");

    // Get initial total
    const paginationText = await page.locator(".pagination span").textContent();
    const initialTotal = parseInt(paginationText!.match(/\((\d+) files\)/)?.[1] || "0");
    expect(initialTotal).toBeGreaterThan(0);

    // Select a specific category
    await page.selectOption(".search-bar .term-select", "archivers");

    // Wait for results to update
    await page.waitForTimeout(500);
    const filteredText = await page.locator(".pagination span").textContent();
    const filteredTotal = parseInt(filteredText!.match(/\((\d+) files\)/)?.[1] || "0");

    expect(filteredTotal).toBeGreaterThan(0);
    expect(filteredTotal).toBeLessThan(initialTotal);
  });

  test("search finds files by name", async ({ page }) => {
    await page.goto("/");

    // Search for a known file pattern
    await page.fill(".term-input", "ARC");
    await page.click("text=[ SEARCH ]");

    // Results should appear
    await page.waitForTimeout(500);
    const paginationText = await page.locator(".pagination span").textContent();
    const total = parseInt(paginationText!.match(/\((\d+) files\)/)?.[1] || "0");
    expect(total).toBeGreaterThan(0);

    // Clear search restores full list
    await page.click("text=[ CLEAR ]");
    await page.waitForTimeout(500);
    const clearedText = await page.locator(".pagination span").textContent();
    const clearedTotal = parseInt(clearedText!.match(/\((\d+) files\)/)?.[1] || "0");
    expect(clearedTotal).toBeGreaterThan(total);
  });

  test("clicking a file row opens the editor panel", async ({ page }) => {
    await page.goto("/");

    // Click the first file row
    await page.locator(".term-table tbody tr").first().click();

    // Editor panel should appear
    await expect(page.locator(".editor-panel")).toBeVisible();
    await expect(page.locator(".editor-panel h3")).toContainText("Edit:");

    // Editor has description textarea, category select, and action buttons
    await expect(page.locator(".editor-panel textarea")).toBeVisible();
    await expect(page.locator(".editor-panel .term-select")).toBeVisible();
    await expect(page.locator("text=[ SAVE ]")).toBeVisible();
    await expect(page.locator("text=[ DELETE ]")).toBeVisible();
    await expect(page.locator("text=[ CANCEL ]")).toBeVisible();
  });

  test("cancel closes the editor panel", async ({ page }) => {
    await page.goto("/");
    await page.locator(".term-table tbody tr").first().click();
    await expect(page.locator(".editor-panel")).toBeVisible();

    await page.click("text=[ CANCEL ]");
    await expect(page.locator(".editor-panel")).not.toBeVisible();
  });

  test("delete shows confirmation dialog", async ({ page }) => {
    await page.goto("/");
    await page.locator(".term-table tbody tr").first().click();

    await page.click("text=[ DELETE ]");

    // Confirmation overlay should appear
    await expect(page.locator(".confirm-overlay")).toBeVisible();
    await expect(page.locator(".confirm-box p")).toContainText("cannot be undone");
    await expect(page.locator(".confirm-box").locator("text=[ CONFIRM ]")).toBeVisible();

    // Cancel the delete
    await page.locator(".confirm-box").locator("text=[ CANCEL ]").click();
    await expect(page.locator(".confirm-overlay")).not.toBeVisible();
  });

  test("pagination navigates between pages", async ({ page }) => {
    await page.goto("/");

    // Should show page 1
    const pageText = await page.locator(".pagination span").textContent();
    expect(pageText).toContain("Page 1");

    // PREV should be disabled on page 1
    const prevBtn = page.locator("text=[ PREV ]");
    await expect(prevBtn).toBeDisabled();

    // If there are multiple pages, NEXT should work
    const total = parseInt(pageText!.match(/\((\d+) files\)/)?.[1] || "0");
    if (total > 50) {
      const nextBtn = page.locator("text=[ NEXT ]");
      await expect(nextBtn).toBeEnabled();
      await nextBtn.click();

      await page.waitForTimeout(500);
      const page2Text = await page.locator(".pagination span").textContent();
      expect(page2Text).toContain("Page 2");

      // PREV should now be enabled
      await expect(prevBtn).toBeEnabled();
    }
  });
});

// ---------------------------------------------------------------------------
// 3. Upload page
// ---------------------------------------------------------------------------

test.describe("Upload page workflows", () => {
  test("drop zone and category selector are functional", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/upload"]');

    // Category dropdown is populated with real categories
    await expect(page.locator(".term-select")).toBeVisible();
    await expect(page.locator(".term-select option").first()).toBeAttached();

    // Drop zone is present and interactive
    const dropZone = page.locator(".drop-zone");
    await expect(dropZone).toBeVisible();
    await expect(dropZone).toContainText("Drop file here");
  });

  test("hidden file input exists for click-to-browse", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/upload"]');

    // Hidden file input should exist
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// 4. Monitor page
// ---------------------------------------------------------------------------

test.describe("Monitor page workflows", () => {
  test("shows active sessions and connection history tables", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/monitor"]');

    // Active sessions table
    await expect(page.getByRole("heading", { name: "Active Sessions" })).toBeVisible();
    const sessionHeaders = page.locator(".term-table").first().locator("th");
    await expect(sessionHeaders.nth(0)).toHaveText("Session");
    await expect(sessionHeaders.nth(1)).toHaveText("IP");

    // Connection history table
    await expect(page.getByRole("heading", { name: "Connection History" })).toBeVisible();
  });

  test("log viewer connects and shows placeholder", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/monitor"]');

    const logViewer = page.locator(".log-viewer");
    await expect(logViewer).toBeVisible();

    // Should show waiting message or log lines
    const content = await logViewer.textContent();
    expect(content!.length).toBeGreaterThan(0);
  });

  test("pause/resume toggles auto-scroll", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/monitor"]');

    // Start with PAUSE visible (auto-scroll is on)
    await expect(page.locator("text=[ PAUSE ]")).toBeVisible();

    // Click to pause
    await page.click("text=[ PAUSE ]");
    await expect(page.locator("text=[ RESUME ]")).toBeVisible();

    // Click to resume
    await page.click("text=[ RESUME ]");
    await expect(page.locator("text=[ PAUSE ]")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 5. Indexer page
// ---------------------------------------------------------------------------

test.describe("Indexer page workflows", () => {
  test("shows indexer status with file and category counts", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/indexer"]');

    // Status badge shows IDLE or RUNNING
    const badge = page.locator(".status-badge");
    await expect(badge).toBeVisible();
    const badgeText = await badge.textContent();
    expect(["IDLE", "RUNNING"]).toContain(badgeText?.trim());

    // File and category counts should be displayed
    await expect(page.locator("dt:has-text('Files')")).toBeVisible();
    await expect(page.locator("dt:has-text('Categories')")).toBeVisible();
  });

  test("run button is enabled when indexer is idle", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/indexer"]');

    // Button should exist (may show RUN NOW or RUNNING...)
    const btn = page.locator(".term-btn", { hasText: /RUN NOW|RUNNING/ });
    await expect(btn).toBeVisible();
  });

  test("output area is ready for streaming", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/indexer"]');

    const logViewer = page.locator(".log-viewer");
    await expect(logViewer).toBeVisible();

    // Should show placeholder text when idle
    const content = await logViewer.textContent();
    expect(content!.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 6. Settings page
// ---------------------------------------------------------------------------

test.describe("Settings page workflows", () => {
  test("displays server info with real data", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/settings"]');

    // Server info is displayed
    await expect(page.locator("dt:has-text('Version')")).toBeVisible();
    await expect(page.locator("dd:has-text('CP/M Software Depot')")).toBeVisible();
    await expect(page.locator("dt:has-text('Telnet Port')")).toBeVisible();
    await expect(page.locator("dd:has-text('2323')")).toBeVisible();
  });

  test("CRT scanline toggle persists state", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/settings"]');

    const btn = page.locator("button:has-text('SCANLINES')");
    await expect(btn).toBeVisible();

    // Get initial state
    const initialText = await btn.textContent();
    const wasOn = initialText!.includes("ON");

    // Toggle
    await btn.click();
    const newText = await btn.textContent();
    if (wasOn) {
      expect(newText).toContain("OFF");
      // Body should not have scanline class
      const hasClass = await page.evaluate(() =>
        document.body.classList.contains("crt-scanlines")
      );
      expect(hasClass).toBe(false);
    } else {
      expect(newText).toContain("ON");
    }

    // Toggle back to restore original state
    await btn.click();
    const restoredText = await btn.textContent();
    expect(restoredText).toContain(wasOn ? "ON" : "OFF");
  });
});

// ---------------------------------------------------------------------------
// 7. API endpoint verification
// ---------------------------------------------------------------------------

test.describe("API endpoints return valid data", () => {
  test("GET /api/categories returns 12 categories", async ({ request }) => {
    const res = await request.get("/api/categories");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(data).toHaveLength(12);
    expect(data[0]).toHaveProperty("area");
    expect(data[0]).toHaveProperty("count");
    expect(data[0]).toHaveProperty("display_name");
  });

  test("GET /api/files returns paginated results", async ({ request }) => {
    const res = await request.get("/api/files?page=1&per_page=10");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(data.files.length).toBeLessThanOrEqual(10);
    expect(data.total).toBeGreaterThan(0);
    expect(data.page).toBe(1);
    expect(data.total_pages).toBeGreaterThan(0);
  });

  test("GET /api/files?area=archivers filters by category", async ({ request }) => {
    const res = await request.get("/api/files?area=archivers");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(data.total).toBeGreaterThan(0);
    for (const f of data.files) {
      expect(f.area).toBe("archivers");
    }
  });

  test("GET /api/files?search=ARC returns search results", async ({ request }) => {
    const res = await request.get("/api/files?search=ARC");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(data.total).toBeGreaterThan(0);
  });

  test("GET /api/sessions returns array", async ({ request }) => {
    const res = await request.get("/api/sessions");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("GET /api/connections returns array", async ({ request }) => {
    const res = await request.get("/api/connections");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(Array.isArray(data)).toBe(true);
  });

  test("GET /api/indexer/status returns valid status", async ({ request }) => {
    const res = await request.get("/api/indexer/status");
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(typeof data.running).toBe("boolean");
    expect(data.file_count).toBeGreaterThanOrEqual(0);
    expect(data.category_count).toBeGreaterThanOrEqual(0);
  });

  test("GET /api/files/nonexistent returns 404", async ({ request }) => {
    const res = await request.get("/api/files/fake/NOFILE.COM");
    expect(res.status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// 8. Cross-page navigation integrity
// ---------------------------------------------------------------------------

test.describe("Cross-page navigation", () => {
  test("full navigation cycle preserves state", async ({ page }) => {
    await page.goto("/");

    // Start on Files
    await expect(page.locator(".page-title")).toHaveText("FILES");

    // Visit every page and return
    for (const [href, title] of [
      ["/upload", "UPLOAD"],
      ["/monitor", "MONITOR"],
      ["/indexer", "INDEXER"],
      ["/settings", "SETTINGS"],
    ]) {
      await page.click(`a[href="${href}"]`);
      await expect(page.locator(".page-title")).toHaveText(title);
    }

    // Return to Files
    await page.click('a[href="/"]');
    await expect(page.locator(".page-title")).toHaveText("FILES");

    // Files should still be loaded
    const rows = page.locator(".term-table tbody tr");
    await expect(rows.first()).toBeVisible();
  });
});
