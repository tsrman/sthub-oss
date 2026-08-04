import { test, expect } from '@playwright/test';
import {
  createApp,
  deleteFromRegistry,
  gotoRegistry,
  runAppFromRegistry,
  stopAppFromRegistry,
} from './helpers';

test.setTimeout(180000);

test('history chips filter events by type', async ({ page }) => {
  const slug = `e2e-hf-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E HF', slug);

  const card = await runAppFromRegistry(page, slug);
  await stopAppFromRegistry(card);

  await page.getByRole('link', { name: 'Deployment history' }).click();
  await page.waitForURL('/streamlits/history');
  await expect(page.locator('text=E2E HF').first()).toBeVisible({ timeout: 10000 });

  // Scope to the event cells: a bare text match would also hit the filter
  // chips, whose labels ("Stops") contain the event labels ("Stop").
  const events = page.getByTestId('history-event');
  const started = events.filter({ hasText: /^Start$/ });
  const stopped = events.filter({ hasText: /^Stop$/ });

  // All events: both run and stop are visible.
  await expect(started.first()).toBeVisible();
  await expect(stopped.first()).toBeVisible();

  // «Stops» keeps only stop events.
  await page.getByRole('button', { name: 'Stops' }).click();
  await expect(stopped.first()).toBeVisible();
  await expect(started).toHaveCount(0);

  // «Deployments» keeps only run events.
  await page.getByRole('button', { name: 'Deployments' }).click();
  await expect(started.first()).toBeVisible();
  await expect(stopped).toHaveCount(0);

  // Back to «All».
  await page.getByRole('button', { name: 'All' }).click();
  await expect(stopped.first()).toBeVisible();

  await deleteFromRegistry(page, slug);
});
