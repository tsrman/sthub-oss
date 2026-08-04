import { test, expect } from '@playwright/test';
import {
  ADMIN_USER,
  AUTH_ADMIN_FILE,
  AUTH_USER_FILE,
  cardBySlug,
  createApp,
  deleteFromRegistry,
  gotoRegistry,
} from './helpers';

test.setTimeout(120000);

test('admin sees the owner filter, regular user does not', async ({ browser }) => {
  const userCtx = await browser.newContext({ storageState: AUTH_USER_FILE });
  const userPage = await userCtx.newPage();
  await gotoRegistry(userPage);
  await expect(
    userPage.getByRole('heading', { name: 'My apps' })
  ).toBeVisible();
  // No owner combobox for a regular user.
  await expect(userPage.getByRole('combobox')).toHaveCount(0);

  const adminCtx = await browser.newContext({ storageState: AUTH_ADMIN_FILE });
  const adminPage = await adminCtx.newPage();
  await gotoRegistry(adminPage, ADMIN_USER);
  await expect(
    adminPage.getByRole('heading', { name: 'All apps' })
  ).toBeVisible();
  await expect(adminPage.getByRole('combobox')).toBeVisible();

  await adminCtx.close();
  await userCtx.close();
});

test('admin sees, filters and deletes another user\'s app', async ({ browser }) => {
  // The regular user creates an app.
  const userCtx = await browser.newContext({ storageState: AUTH_USER_FILE });
  const userPage = await userCtx.newPage();
  const slug = `e2e-admin-${Date.now()}`;
  await gotoRegistry(userPage);
  await createApp(userPage, 'E2E Admin', slug);

  // The admin sees it in the global registry.
  const adminCtx = await browser.newContext({ storageState: AUTH_ADMIN_FILE });
  const adminPage = await adminCtx.newPage();
  await gotoRegistry(adminPage, ADMIN_USER);
  const card = cardBySlug(adminPage, slug);
  await expect(card).toBeVisible({ timeout: 15000 });

  // Filtering by the owner's login keeps the card visible.
  await adminPage.getByRole('combobox').selectOption('testuser');
  await expect(cardBySlug(adminPage, slug)).toBeVisible({ timeout: 10000 });

  // The admin is allowed to delete the foreign app.
  await deleteFromRegistry(adminPage, slug);

  // And it is gone for the owner too.
  await userPage.goto('/streamlits');
  await expect(cardBySlug(userPage, slug)).not.toBeVisible({ timeout: 15000 });

  await adminCtx.close();
  await userCtx.close();
});
