import { test, expect } from '@playwright/test';
import { cardBySlug, createApp, deleteFromRegistry, gotoRegistry } from './helpers';

test.setTimeout(120000);

test('registry search filters cards by name', async ({ page }) => {
  const slug = `e2e-search-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'UniqueSearchName', slug);

  await page.goto('/streamlits');
  const search = page.locator('input[placeholder="Search by name or URL…"]');

  // Match by name.
  await search.fill('UniqueSearchName');
  await expect(cardBySlug(page, slug)).toBeVisible({ timeout: 10000 });

  // No match → the card disappears from the list.
  await search.fill('definitely-no-such-app-zzz');
  await expect(cardBySlug(page, slug)).not.toBeVisible({ timeout: 10000 });

  await search.fill('');
  await deleteFromRegistry(page, slug);
});

test('registry status chips filter cards', async ({ page }) => {
  const slug = `e2e-chip-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Chip', slug);

  // The new app is stopped: visible under «Stopped», hidden under «Running».
  await page.goto('/streamlits');
  await page.getByRole('button', { name: 'Stopped' }).click();
  await expect(cardBySlug(page, slug)).toBeVisible({ timeout: 10000 });

  await page.getByRole('button', { name: 'Running' }).click();
  await expect(cardBySlug(page, slug)).not.toBeVisible({ timeout: 10000 });

  await page.getByRole('button', { name: 'All' }).click();
  await expect(cardBySlug(page, slug)).toBeVisible({ timeout: 10000 });

  await deleteFromRegistry(page, slug);
});

test('duplicate from the card menu creates a copy', async ({ page }) => {
  const slug = `e2e-dup-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Dup', slug);

  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-duplicate').click();

  // The copy appears with a -copy slug (list refreshes every 5s).
  const copy = cardBySlug(page, `${slug}-copy`);
  await expect(copy).toBeVisible({ timeout: 20000 });
  await expect(copy).toContainText('E2E Dup');

  await deleteFromRegistry(page, `${slug}-copy`);
  await deleteFromRegistry(page, slug);
});

test('card menu navigates to logs and settings', async ({ page }) => {
  const slug = `e2e-nav-${Date.now()}`;
  await gotoRegistry(page);
  const appId = await createApp(page, 'E2E Nav', slug);

  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);

  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-logs').click();
  await page.waitForURL(`/streamlits/${appId}/logs`);
  await expect(page.getByTestId('clear-logs-button')).toBeVisible();

  await page.goto('/streamlits');
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-settings').click();
  await page.waitForURL(`/streamlits/${appId}/settings`);
  await expect(page.getByRole('heading', { name: 'App settings' })).toBeVisible();

  await deleteFromRegistry(page, slug);
});
