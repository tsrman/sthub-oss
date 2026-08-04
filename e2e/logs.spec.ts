import { test, expect } from '@playwright/test';
import {
  createApp,
  deleteFromRegistry,
  gotoRegistry,
  runAppFromRegistry,
  stopAppFromRegistry,
} from './helpers';

test.setTimeout(180000);

test('logs page streams lines and supports clear/follow/pause controls', async ({
  page,
}) => {
  const slug = `e2e-logs-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Logs', slug);

  const card = await runAppFromRegistry(page, slug);

  // Open logs via the card menu.
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-logs').click();
  await page.waitForURL(/\/streamlits\/[^/]+\/logs/);

  // Header shows the app name and its status.
  await expect(page.locator('header').getByText('E2E Logs')).toBeVisible();

  // Log lines stream in (build lines at minimum).
  await expect(page.getByTestId('log-line').first()).toBeVisible({ timeout: 30000 });
  expect(await page.getByTestId('log-line').count()).toBeGreaterThan(0);

  // The stream is connected.
  await expect(page.locator('text=● live')).toBeVisible({ timeout: 15000 });

  // Clear empties the view (client-side).
  await page.getByTestId('clear-logs-button').click();
  await expect(page.getByTestId('log-line')).toHaveCount(0);

  // Follow toggle switches its visual state.
  const follow = page.getByTestId('follow-toggle');
  const classBefore = await follow.getAttribute('class');
  await follow.click();
  await expect(follow).not.toHaveClass(classBefore!);

  // Pause toggle flips its label and stops the stream indicator.
  const pause = page.getByTestId('pause-toggle');
  await expect(pause).toHaveText(/Pause/);
  await pause.click();
  await expect(pause).toHaveText(/Resume/);
  await expect(page.locator('text=○ offline')).toBeVisible();

  // Cleanup.
  await page.goto('/streamlits');
  await stopAppFromRegistry(card);
  await deleteFromRegistry(page, slug);
});
