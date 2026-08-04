import { test, expect } from '@playwright/test';
import { deleteFromRegistry, gotoRegistry } from './helpers';

test.setTimeout(120000);

test('create form normalizes an invalid slug and checks availability', async ({
  page,
}) => {
  const slug = `e2e-valid-${Date.now()}`;
  await gotoRegistry(page);

  await page.click('text=+ Create app');
  await page.waitForURL('/streamlits/new');

  const slugInput = page.locator('input[placeholder="my-app"]');

  // Uppercase/spaces/special chars are normalized to [a-z0-9-] on the fly.
  await slugInput.fill('My App!!');
  await expect(slugInput).toHaveValue('my-app');
  await expect(page.locator('text=✓ Address available')).toBeVisible({ timeout: 10000 });

  // A fresh slug also passes the availability check.
  await slugInput.fill(slug);
  await expect(page.locator('text=✓ Address available')).toBeVisible({ timeout: 10000 });

  // Create the app, then try to reuse the same slug in another create form.
  await page.fill('input[name="name"]', 'E2E Valid');
  await page.click('text=Create and open editor');
  await page.waitForURL(/\/streamlits\/[^/]+\/editor/, { timeout: 15000 });

  // Navigate client-side (a full reload can bounce through a 401 → SSO roundtrip).
  await page.getByRole('link', { name: '← Back' }).click();
  await page.waitForURL('/streamlits');
  await page.click('text=+ Create app');
  await page.waitForURL('/streamlits/new');
  await slugInput.fill(slug);
  await expect(page.locator('text=✕ Address taken')).toBeVisible({ timeout: 10000 });

  // Submit is blocked while the slug is taken: no navigation happens.
  await page.fill('input[name="name"]', 'E2E Valid 2');
  await page.click('text=Create and open editor');
  await page.waitForTimeout(1500);
  expect(page.url()).toContain('/streamlits/new');

  await deleteFromRegistry(page, slug);
});

test('create form requires a name', async ({ page }) => {
  await gotoRegistry(page);
  await page.click('text=+ Create app');
  await page.waitForURL('/streamlits/new');

  // Native required-validation keeps the form from submitting without a name.
  await page.locator('input[placeholder="my-app"]').fill(`e2e-noname-${Date.now()}`);
  await page.click('text=Create and open editor');
  await page.waitForTimeout(1500);
  expect(page.url()).toContain('/streamlits/new');
});
