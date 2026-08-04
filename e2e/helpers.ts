import { expect, type Locator, type Page } from '@playwright/test';

export const TEST_USER = { username: 'testuser', password: 'testpass' };
export const ADMIN_USER = { username: 'adminuser', password: 'adminpass' };

export const AUTH_USER_FILE = '.auth/user.json';
export const AUTH_ADMIN_FILE = '.auth/admin.json';
export const STHUB_BASE_URL = process.env.STHUB_BASE_URL ?? 'http://localhost:3001';
export const KEYCLOAK_URL = process.env.STHUB_KEYCLOAK_URL ?? 'http://localhost:8080';
export const isKeycloakURL = (url: URL) => url.origin === KEYCLOAK_URL;

/** Perform the full Keycloak UI login flow starting from /login. */
export async function login(page: Page, user = TEST_USER): Promise<void> {
  await page.goto('/login');
  await page.waitForURL(isKeycloakURL, { timeout: 15000 });
  await page.fill('#username', user.username);
  await page.fill('#password', user.password);
  await page.click('#kc-login');
  await page.waitForURL('/streamlits', { timeout: 20000 });
}

/**
 * Open the registry page. With a live SSO session (storageState) check-sso
 * lands on the registry directly; otherwise the app bounces to Keycloak and
 * we fall back to the UI login form.
 */
export async function gotoRegistry(page: Page, user = TEST_USER): Promise<void> {
  await page.goto('/streamlits');
  const landedOnKeycloak = await page
    .waitForURL(isKeycloakURL, { timeout: 8000 })
    .then(() => true)
    .catch(() => false);
  if (landedOnKeycloak) {
    await page.fill('#username', user.username);
    await page.fill('#password', user.password);
    await page.click('#kc-login');
  }
  await page.waitForURL('/streamlits', { timeout: 20000 });
  // Admins see the «All apps» heading instead of «My apps».
  await expect(
    page.getByRole('heading', { name: /^(My|All) apps$/ })
  ).toBeVisible({ timeout: 15000 });
}

/** Create an app via the registry UI; lands in the editor. Returns the app id. */
export async function createApp(page: Page, name: string, slug: string): Promise<string> {
  await page.click('text=+ Create app');
  await page.waitForURL('/streamlits/new');
  await page.fill('input[name="name"]', name);
  await page.fill('input[placeholder="my-app"]', slug);
  await page.click('text=Create and open editor');
  await page.waitForURL(/\/streamlits\/[^/]+\/editor/, { timeout: 15000 });
  return page.url().match(/streamlits\/([^/]+)\/editor/)![1];
}

/** Locate the registry card of the app with the given (unique) slug. */
export function cardBySlug(page: Page, slug: string): Locator {
  return page.getByTestId('app-card').filter({ hasText: slug }).first();
}

/** Wait until the card shows the given status label. */
export async function waitForStatus(
  card: Locator,
  label: RegExp,
  timeout = 90000
): Promise<void> {
  await expect(card.getByTestId('status-badge')).toHaveText(label, { timeout });
}

/** Run the app from its registry card and wait until it is running. */
export async function runAppFromRegistry(page: Page, slug: string): Promise<Locator> {
  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);
  await expect(card).toBeVisible({ timeout: 20000 });
  await card.getByTestId('run-button').click();
  await waitForStatus(card, /^Running$/);
  return card;
}

/** Stop the app from its registry card and wait until it is stopped. */
export async function stopAppFromRegistry(card: Locator): Promise<void> {
  await card.getByTestId('stop-button').click();
  await waitForStatus(card, /^Stopped$/, 30000);
}

/** Delete the app through the card menu + confirmation modal. */
export async function deleteFromRegistry(page: Page, slug: string): Promise<void> {
  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);
  await expect(card).toBeVisible({ timeout: 20000 });
  await card.getByTestId('card-menu-button').click();
  await card.getByTestId('menu-delete').click();
  await expect(page.locator('text=Delete app?')).toBeVisible();
  await page.getByRole('button', { name: 'Delete' }).click();
  await expect(cardBySlug(page, slug)).not.toBeVisible({ timeout: 15000 });
}
