import { test, expect, type BrowserContext } from '@playwright/test';
import {
  cardBySlug,
  createApp,
  deleteFromRegistry,
  gotoRegistry,
  runAppFromRegistry,
  stopAppFromRegistry,
  waitForStatus,
} from './helpers';

test.setTimeout(120000);

/**
 * Open the app through Traefik and wait for the Streamlit UI.
 *
 * Retry on the app's own content rather than on the response status: right
 * after a (re)start Traefik may answer 502 while it swaps the backend
 * container, and until it has picked up the new container's labels the request
 * falls through to the frontend's 404 page — which is a 404, not a 5xx, so a
 * status check would accept it and then wait out the timeout on a dead page.
 */
async function openAppWithRetry(context: BrowserContext, href: string) {
  const appPage = await context.newPage();
  await expect(async () => {
    await appPage.goto(href);
    await expect(appPage.locator('text=Hello!')).toBeVisible({ timeout: 5000 });
  }).toPass({ timeout: 90000, intervals: [2000, 3000, 5000] });
  await appPage.close();
}

test('create, run, open and delete a streamlit app', async ({ page, context }) => {
  const slug = `e2e-${Date.now()}`;

  await gotoRegistry(page);

  // Create app
  await createApp(page, 'E2E Lifecycle', slug);

  // Run from registry
  const card = await runAppFromRegistry(page, slug);

  // Open app via Traefik
  const appHref = await card.locator('a[href^="/st/"]').getAttribute('href');
  expect(appHref).toMatch(/^\/st\//);
  await openAppWithRetry(context, appHref!);

  // Stop
  await stopAppFromRegistry(card);

  // Delete (menu → confirmation modal)
  await deleteFromRegistry(page, slug);
});

test('deployment history records run and stop events', async ({ page }) => {
  const slug = `e2e-history-${Date.now()}`;

  await gotoRegistry(page);
  await createApp(page, 'E2E History', slug);

  // Run from registry
  const card = await runAppFromRegistry(page, slug);

  // Stop
  await stopAppFromRegistry(card);

  // Check history page (use client-side nav to keep Keycloak session)
  await page.getByRole('link', { name: 'Deployment history' }).click();
  await page.waitForURL('/streamlits/history');
  await expect(page.getByRole('heading', { name: 'Deployment history' })).toBeVisible();
  await expect(page.locator('text=E2E History').first()).toBeVisible({ timeout: 10000 });
  await expect(page.locator('text=Start').first()).toBeVisible();
  await expect(page.locator('text=Stop').first()).toBeVisible();

  // Cleanup
  await deleteFromRegistry(page, slug);
});

test('restart a running app keeps it serving', async ({ page, context }) => {
  test.setTimeout(180000);
  const slug = `e2e-restart-${Date.now()}`;

  await gotoRegistry(page);
  await createApp(page, 'E2E Restart', slug);

  const card = await runAppFromRegistry(page, slug);

  // Restart from the card: building → running again.
  await card.getByTestId('restart-button').click();
  await waitForStatus(card, /^Running$/);

  // The app still serves through Traefik after the restart.
  const appHref = await card.locator('a[href^="/st/"]').getAttribute('href');
  await openAppWithRetry(context, appHref!);

  await stopAppFromRegistry(card);
  await deleteFromRegistry(page, slug);
});
