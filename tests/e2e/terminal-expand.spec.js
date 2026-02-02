/**
 * E2E Tests for Terminal Expand Feature
 * Playwright browser tests for mobile workshop page
 */

const { test, expect } = require('@playwright/test');

test.describe('Terminal Expand Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/m/workshop');
    await page.waitForSelector('.terminal-chat-container');
  });

  // Test 31: Page loads without console errors
  test('page should load without JavaScript errors', async ({ page }) => {
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.reload();
    await page.waitForSelector('.terminal-chat-container');
    expect(errors).toHaveLength(0);
  });

  // Test 32: Both expand bars are visible
  test('both terminal expand bars should be visible', async ({ page }) => {
    await expect(page.locator('#terminal1-label')).toBeVisible();
    await expect(page.locator('#terminal2-label')).toBeVisible();
  });

  // Test 33: Terminal 1 bar shows correct initial text
  test('Terminal 1 bar should show "Expand Terminal 1"', async ({ page }) => {
    await expect(page.locator('#terminal1-label')).toHaveText('Expand Terminal 1');
  });

  // Test 34: Clicking Terminal 1 bar expands it
  test('clicking Terminal 1 bar should expand terminal', async ({ page }) => {
    await page.click('#terminal1-label');
    await expect(page.locator('#terminal1-inline-wrapper')).toHaveClass(/expanded/);
    await expect(page.locator('#terminal1-label')).toHaveText('Collapse Terminal 1');
  });

  // Test 35: Terminal 1 iframe loads correct URL
  test('Terminal 1 iframe should load port 7681', async ({ page }) => {
    await page.click('#terminal1-label');
    const frame = page.locator('#terminal1-inline-frame');
    await expect(frame).toHaveAttribute('src', /7681/);
  });

  // Test 36: Clicking again collapses Terminal 1
  test('clicking Terminal 1 bar again should collapse it', async ({ page }) => {
    await page.click('#terminal1-label');
    await page.click('#terminal1-label');
    await expect(page.locator('#terminal1-inline-wrapper')).not.toHaveClass(/expanded/);
    await expect(page.locator('#terminal1-label')).toHaveText('Expand Terminal 1');
  });

  // Test 37: Both terminals can be expanded together
  test('both terminals can be expanded simultaneously', async ({ page }) => {
    await page.click('#terminal1-label');
    await page.click('#terminal2-label');
    await expect(page.locator('#terminal1-inline-wrapper')).toHaveClass(/expanded/);
    await expect(page.locator('#terminal2-inline-wrapper')).toHaveClass(/expanded/);
  });

  // Test 38: Chat input still works with terminals expanded
  test('chat input should still be functional', async ({ page }) => {
    await page.click('#terminal1-label');
    const input = page.locator('#chat-input');
    await expect(input).toBeVisible();
    await expect(input).toBeEnabled();
  });

  // Test 39: Window selector still works
  test('window selector should still be visible and functional', async ({ page }) => {
    const selector = page.locator('#window-selector');
    await expect(selector).toBeVisible();
  });

  // Test 40: Terminal 1 appears before Terminal 2 visually
  test('Terminal 1 expand bar should be above Terminal 2', async ({ page }) => {
    const t1Box = await page.locator('#terminal1-label').boundingBox();
    const t2Box = await page.locator('#terminal2-label').boundingBox();
    expect(t1Box.y).toBeLessThan(t2Box.y);
  });
});
