import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  workers: 1,
  reporter: 'list',
  outputDir: '../.cache/browser-tests',
  use: {
    baseURL: process.env.VIDDL_TEST_URL || 'http://127.0.0.1:8000',
    headless: true,
    channel: process.platform === 'win32' ? 'chrome' : undefined,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1024, height: 1536 }, deviceScaleFactor: 1 } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true } },
  ],
});
