/**
 * E2E Tests for Summary Filter Feature
 * Tests the synthesized summary view in terminal chat
 */

const { test, expect } = require('@playwright/test');

test.describe('Summary Filter Feature', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/m/workshop');
    await page.waitForSelector('.terminal-chat-container');
  });

  test('filter button should be visible in chat header', async ({ page }) => {
    const filterBtn = page.locator('#summary-filter-btn');
    await expect(filterBtn).toBeVisible();
  });

  test('filter button should have correct title attribute', async ({ page }) => {
    const filterBtn = page.locator('#summary-filter-btn');
    await expect(filterBtn).toHaveAttribute('title', 'Show summaries only');
  });

  test('filter button toggles active state on click', async ({ page }) => {
    const filterBtn = page.locator('#summary-filter-btn');

    // Initially not active
    await expect(filterBtn).not.toHaveClass(/active/);

    // Click to activate
    await filterBtn.click();
    await expect(filterBtn).toHaveClass(/active/);

    // Click again to deactivate
    await filterBtn.click();
    await expect(filterBtn).not.toHaveClass(/active/);
  });

  test('filter button has correct styling when active', async ({ page }) => {
    const filterBtn = page.locator('#summary-filter-btn');
    await filterBtn.click();

    // Check active state has gold border
    await expect(filterBtn).toHaveCSS('border-color', /rgb\(212, 175, 55\)|gold/i);
  });
});

test.describe('Summary Message Rendering', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the API response with mixed message types
    await page.route('/api/terminal/chat/buffer*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            { type: 'user', content: 'deploy the app' },
            { type: 'tool', content: 'Bash(deploy.sh)', tool_name: 'Bash', collapsed: true },
            { type: 'summary', content: 'Deployment successful!\n\nURL: https://example.com', collapsed: false },
            { type: 'tool', content: 'Read(status.json)', tool_name: 'Read', collapsed: true },
            { type: 'summary', content: 'Service is healthy. All checks passed.', collapsed: false }
          ],
          state: 'done'
        })
      });
    });

    // Also mock the state endpoint
    await page.route('/api/terminal/chat/state*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ state: 'idle' })
      });
    });

    // Mock windows endpoint
    await page.route('/api/terminal/windows', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          windows: [{ id: '1', name: 'Terminal 1', active: true }]
        })
      });
    });

    await page.goto('/m/workshop');
    await page.waitForSelector('.terminal-chat-container');
    // Wait for messages to render
    await page.waitForSelector('.chat-message', { timeout: 5000 });
  });

  test('summary messages have correct class', async ({ page }) => {
    const summaryMessages = page.locator('.chat-message.summary');
    await expect(summaryMessages.first()).toBeVisible();
    expect(await summaryMessages.count()).toBe(2);
  });

  test('summary messages display with summary-bubble element', async ({ page }) => {
    const summaryBubble = page.locator('.summary-bubble').first();
    await expect(summaryBubble).toBeVisible();
  });

  test('summary messages have icon', async ({ page }) => {
    const summaryIcon = page.locator('.summary-icon').first();
    await expect(summaryIcon).toBeVisible();
    await expect(summaryIcon).toContainText('●');
  });

  test('tool messages are hidden when filter is active', async ({ page }) => {
    // Verify tools are visible initially
    await expect(page.locator('.chat-message.tool').first()).toBeVisible();

    // Activate filter
    await page.click('#summary-filter-btn');

    // Tools should be hidden
    await expect(page.locator('.chat-message.tool')).not.toBeVisible();

    // Summaries should still be visible
    await expect(page.locator('.chat-message.summary').first()).toBeVisible();
  });

  test('user messages remain visible when filter is active', async ({ page }) => {
    // Verify user message is visible initially
    await expect(page.locator('.chat-message.user')).toBeVisible();

    // Activate filter
    await page.click('#summary-filter-btn');

    // User message should still be visible
    await expect(page.locator('.chat-message.user')).toBeVisible();
  });

  test('disabling filter shows all messages again', async ({ page }) => {
    // Activate filter
    await page.click('#summary-filter-btn');
    await expect(page.locator('.chat-message.tool')).not.toBeVisible();

    // Deactivate filter
    await page.click('#summary-filter-btn');

    // Tools should be visible again
    await expect(page.locator('.chat-message.tool').first()).toBeVisible();
  });
});

test.describe('Summary Message Content Formatting', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('/api/terminal/chat/buffer*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            {
              type: 'summary',
              content: 'Changes complete:\n- Added `feature.js`\n- Updated **config**\n- Fixed bug',
              collapsed: false
            }
          ],
          state: 'done'
        })
      });
    });

    await page.route('/api/terminal/chat/state*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ state: 'idle' })
      });
    });

    await page.route('/api/terminal/windows', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          windows: [{ id: '1', name: 'Terminal 1', active: true }]
        })
      });
    });

    await page.goto('/m/workshop');
    await page.waitForSelector('.chat-message.summary', { timeout: 5000 });
  });

  test('inline code is rendered correctly', async ({ page }) => {
    const codeElement = page.locator('.summary-content code');
    await expect(codeElement.first()).toBeVisible();
  });

  test('bold text is rendered correctly', async ({ page }) => {
    const strongElement = page.locator('.summary-content strong');
    await expect(strongElement).toBeVisible();
    await expect(strongElement).toContainText('config');
  });

  test('bullet lists are rendered', async ({ page }) => {
    const listItems = page.locator('.summary-content li');
    expect(await listItems.count()).toBeGreaterThan(0);
  });
});

test.describe('Summary with ASCII Tables', () => {
  test('ASCII tables are preserved in pre element', async ({ page }) => {
    await page.route('/api/terminal/chat/buffer*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            {
              type: 'summary',
              content: '┌────────┬─────────┐\n│ Status │ Details │\n└────────┴─────────┘',
              collapsed: false
            }
          ],
          state: 'done'
        })
      });
    });

    await page.route('/api/terminal/chat/state*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ state: 'idle' })
      });
    });

    await page.route('/api/terminal/windows', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          windows: [{ id: '1', name: 'Terminal 1', active: true }]
        })
      });
    });

    await page.goto('/m/workshop');
    await page.waitForSelector('.summary-table', { timeout: 5000 });

    const table = page.locator('.summary-table');
    await expect(table).toBeVisible();
    await expect(table).toContainText('Status');
  });
});

test.describe('Empty State with Filter', () => {
  test('shows appropriate message when no summaries exist', async ({ page }) => {
    await page.route('/api/terminal/chat/buffer*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [
            { type: 'tool', content: 'Bash(ls)', tool_name: 'Bash', collapsed: true }
          ],
          state: 'done'
        })
      });
    });

    await page.route('/api/terminal/chat/state*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ state: 'idle' })
      });
    });

    await page.route('/api/terminal/windows', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          windows: [{ id: '1', name: 'Terminal 1', active: true }]
        })
      });
    });

    await page.goto('/m/workshop');
    await page.waitForSelector('.chat-message.tool', { timeout: 5000 });

    // Activate filter
    await page.click('#summary-filter-btn');

    // Should show empty state message
    const emptyState = page.locator('.chat-messages-empty');
    await expect(emptyState).toBeVisible();
    await expect(emptyState).toContainText('No summaries yet');
  });
});
