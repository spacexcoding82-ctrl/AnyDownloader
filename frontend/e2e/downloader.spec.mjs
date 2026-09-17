import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

test('homepage, responsive layout, validation and navigation', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', e => { if (e.type() === 'error') errors.push(e.text()); });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Download Videos from Any Platform' })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await fs.mkdir('../docs/qa', { recursive: true });
  await page.screenshot({ path: `../docs/qa/${testInfo.project.name}.png`, fullPage: true });
  await page.locator('.hero').screenshot({ path: `../docs/qa/${testInfo.project.name}-hero.png` });
  const widths = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
  await page.getByLabel('Video link', { exact: true }).fill('not-a-link');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('complete video link');
  await page.getByLabel('Clear video link', { exact: true }).click();
  await page.getByRole('button', { name: 'Privacy', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'Pinterest', exact: true }).click();
  await expect(page.locator('.platform-detail')).toContainText('pinterest.com/pin/');
  await page.getByRole('button', { name: 'Try a link' }).click();
  await expect(page.getByLabel('Video link', { exact: true })).toBeFocused();
  if (testInfo.project.name === 'mobile') {
    await page.getByRole('button', { name: 'Open navigation' }).click();
    await page.getByRole('navigation').getByRole('link', { name: 'Supported Sites' }).click();
    await expect(page.getByRole('navigation')).toBeHidden();
  }
  expect(errors).toEqual([]);
});

test('quality selection, confirmation and progress', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let selected;
  let polls = 0;
  await page.route('**/api/inspect', route => route.fulfill({ json: {
    inspection_id: 'browser-fixture', title: 'An afternoon in the garden', platform: 'Test fixture', duration: 16,
    thumbnail: null, formats: [
      { key: '1080', label: '1080p', height: 1080, container: 'mp4', has_audio: true, size_bytes: 20_000_000 },
      { key: '720', label: '720p', height: 720, container: 'mp4', has_audio: true, size_bytes: 10_000_000 },
    ],
  } }));
  await page.route('**/api/download', async route => {
    selected = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { job_id: 'browser-job', status: 'queued' } });
  });
  await page.route('**/api/jobs/browser-job', async route => {
    polls++;
    await route.fulfill({ json: polls < 3 ? { job_id: 'browser-job', status: 'downloading', progress: 40, downloaded_bytes: 4_000_000 } : { job_id: 'browser-job', status: 'ready', progress: 100, size_bytes: 10, file_url: '/api/jobs/browser-job/file' } });
  });
  await page.goto('/');
  await page.getByLabel('Video link', { exact: true }).fill('https://example.com/test-video');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'An afternoon in the garden' })).toBeVisible();
  await page.getByRole('button', { name: /720p MP4/ }).click();
  const prepare = page.getByRole('button', { name: 'Download 720p MP4', exact: true });
  await expect(prepare).toBeDisabled();
  await page.getByRole('checkbox').check();
  await expect(prepare).toBeEnabled();
  await page.screenshot({ path: `../docs/qa/${testInfo.project.name}-qualities.png`, fullPage: true });
  await prepare.click();
  await expect(page.getByRole('progressbar')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Save video to device' })).toBeVisible();
  expect(selected.format_key).toBe('720');
  expect(selected.rights_confirmed).toBe(true);
  // Chromium's download manager does not honor Playwright page route mocks.
  // The actual file transfer is tested below against the real API and media.
  await expect(page.getByRole('link', { name: 'Save video to device' })).toHaveAttribute('href', '/api/jobs/browser-job/file');
  expect(errors).toEqual([]);
});

test('real public sample saves a playable video through the actual backend', async ({ page }, testInfo) => {
  test.skip(process.env.VIDDL_LIVE_TEST !== '1', 'Explicit opt-in: this test downloads the small MDN public example.');
  test.setTimeout(120_000);
  await page.goto('/');
  await page.getByLabel('Video link', { exact: true }).fill('https://developer.mozilla.org/shared-assets/videos/flower.mp4');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'flower', exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Download 540p MP4', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Save video to device' })).toBeVisible({ timeout: 60_000 });
  const pending = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Save video to device' }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe('flower.mp4');
  expect(await download.failure()).toBeNull();
  const saved = testInfo.outputPath('flower.mp4');
  await download.saveAs(saved);
  expect((await fs.stat(saved)).size).toBeGreaterThan(1_000_000);
  await expect(page.getByText('Sent to your browser', { exact: true })).toBeVisible();
  await page.screenshot({ path: `../docs/qa/${testInfo.project.name}-download.png`, fullPage: true });
});

test('small screens, tablet and zoom-equivalent viewport preserve usable controls', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Download', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 768, height: 1024 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // Browser zoom reduces the CSS viewport; CSS `zoom` does not update media
  // queries and is not an equivalent accessibility test. Emulate 768px at 200%.
  await page.setViewportSize({ width: 384, height: 512 });
  await expect(page.getByRole('button', { name: 'Download', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('backend errors are visible and editing a link resets results', async ({ page }) => {
  await page.route('**/api/inspect', route => route.fulfill({ status: 400, json: { error: { code: 'login_required', message: 'This video requires a login.' } } }));
  await page.goto('/');
  await page.getByLabel('Video link', { exact: true }).fill('https://example.com/private');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('requires a login');
  await page.getByLabel('Video link', { exact: true }).fill('https://example.com/new');
  await expect(page.getByRole('alert')).toHaveCount(0);
});
