import { test, expect } from '@playwright/test';
import { cardBySlug, createApp, deleteFromRegistry, gotoRegistry } from './helpers';

test.setTimeout(120000);

test('apply a template, edit in the editor, check syntax and create a file', async ({
  page,
}) => {
  await gotoRegistry(page);

  // Apply the blank template → lands in the editor.
  await page.getByRole('link', { name: 'Templates' }).click();
  await page.waitForURL('/streamlits/templates');
  const tpl = page.getByTestId('template-card').filter({ hasText: 'Blank app' }).first();
  await tpl.getByRole('button', { name: 'Use template' }).click();
  await page.waitForURL(/\/streamlits\/[^/]+\/editor/, { timeout: 15000 });
  const appId = page.url().match(/streamlits\/([^/]+)\/editor/)![1];

  // Editor shell is present with the file tree.
  await expect(page.getByText('Project files')).toBeVisible();
  await expect(page.getByText('app.py')).toBeVisible();

  // Syntax check opens the problems panel.
  await page.getByTestId('check-button').click();
  await expect(page.getByText('Problems')).toBeVisible();

  // Create a new file via the prompt dialog.
  page.once('dialog', (dialog) => dialog.accept('utils.py'));
  await page.getByTitle('New file').click();
  await expect(page.getByText('utils.py')).toBeVisible({ timeout: 10000 });

  // Cleanup: scope to the exact app created by this test (by editor link).
  await page.getByRole('link', { name: '← Back' }).click();
  await page.waitForURL('/streamlits');
  const card = page
    .getByTestId('app-card')
    .filter({ has: page.locator(`a[href="/streamlits/${appId}/editor"]`) });
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-delete').click();
  await expect(page.locator('text=Delete app?')).toBeVisible();
  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(card).not.toBeVisible({ timeout: 10000 });
});

test('delete confirmation modal can be cancelled', async ({ page }) => {
  const slug = `e2e-cancel-${Date.now()}`;
  await gotoRegistry(page);

  await createApp(page, 'E2E Cancel', slug);

  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);
  await expect(card).toBeVisible({ timeout: 20000 });

  // Open the delete modal, then cancel — the app must remain.
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-delete').click();
  await expect(page.locator('text=Delete app?')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.locator('text=Delete app?')).not.toBeVisible();
  await expect(card).toBeVisible();

  // Cleanup: confirm deletion this time.
  await deleteFromRegistry(page, slug);
});
