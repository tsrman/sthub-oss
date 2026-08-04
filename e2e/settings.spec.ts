import { test, expect } from '@playwright/test';
import { cardBySlug, createApp, deleteFromRegistry, gotoRegistry } from './helpers';

test.setTimeout(120000);

test('settings page updates name, slug and description', async ({ page }) => {
  const slug = `e2e-set-${Date.now()}`;
  // Must NOT contain the original slug as a substring (card filter is by text).
  const newSlug = `e2e-ren-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Settings', slug);

  // Open settings via the card menu.
  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-settings').click();
  await page.waitForURL(/\/streamlits\/[^/]+\/settings/);
  await expect(page.getByRole('heading', { name: 'App settings' })).toBeVisible();

  // Rename.
  await page.getByTestId('settings-name-input').fill('E2E Settings Renamed');
  // Change the slug; wait for the availability check to confirm it is free.
  await page.locator('input[placeholder="my-app"]').fill(newSlug);
  await expect(page.locator('text=✓ Address available')).toBeVisible({ timeout: 10000 });
  // Description.
  await page.locator('textarea').fill('Description for the e2e test');

  await page.getByRole('button', { name: 'Save' }).click();
  await page.waitForURL('/streamlits', { timeout: 15000 });

  // Registry shows the renamed app under the new slug with the description.
  const renamed = cardBySlug(page, newSlug);
  await expect(renamed).toBeVisible({ timeout: 20000 });
  await expect(renamed).toContainText('E2E Settings Renamed');
  await expect(renamed).toContainText('Description for the e2e test');
  await expect(cardBySlug(page, slug)).not.toBeVisible();

  await deleteFromRegistry(page, newSlug);
});

test('settings reject a slug that is already taken', async ({ page }) => {
  const slugA = `e2e-taken-a-${Date.now()}`;
  const slugB = `e2e-taken-b-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Taken A', slugA);
  await page.goto('/streamlits');
  await createApp(page, 'E2E Taken B', slugB);

  // Open settings of app B and try to take the slug of app A.
  await page.goto('/streamlits');
  const card = cardBySlug(page, slugB);
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-settings').click();
  await page.waitForURL(/\/streamlits\/[^/]+\/settings/);

  await page.locator('input[placeholder="my-app"]').fill(slugA);
  await expect(page.locator('text=✕ Address taken')).toBeVisible({ timeout: 10000 });

  // Submit is a no-op while the slug is taken: we stay on the settings page.
  await page.getByRole('button', { name: 'Save' }).click();
  await page.waitForTimeout(1500);
  expect(page.url()).toMatch(/\/settings/);

  // Cleanup both apps.
  await deleteFromRegistry(page, slugA);
  await deleteFromRegistry(page, slugB);
});
