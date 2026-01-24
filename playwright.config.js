const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:3003',
    headless: true,
    viewport: { width: 390, height: 844 }, // iPhone 14 Pro
  },
  projects: [
    { name: 'mobile-chrome', use: { browserName: 'chromium' } }
  ]
});
