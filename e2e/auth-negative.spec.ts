import { test, expect } from '@playwright/test';
import { AUTH_USER_FILE, isKeycloakURL, KEYCLOAK_URL, STHUB_BASE_URL } from './helpers';

// These scenarios need a fresh, unauthenticated context by default.
test.use({ storageState: { cookies: [], origins: [] } });

test('wrong password shows a Keycloak error', async ({ page }) => {
  await page.goto('/login');
  await page.waitForURL(isKeycloakURL, { timeout: 15000 });
  await page.fill('#username', 'testuser');
  await page.fill('#password', 'definitely-wrong');
  await page.click('#kc-login');

  // We stay on Keycloak with an error message, no redirect into the app.
  // Match the message rather than the element id: Keycloak moves the id between
  // releases (#input-error in 25, per-field ids in 26).
  await expect(page.getByText(/invalid username or password/i)).toBeVisible({
    timeout: 10000,
  });
  expect(page.url()).toContain(KEYCLOAK_URL);
});

test('unauthenticated visit to /streamlits redirects to login', async ({ page }) => {
  await page.goto('/streamlits');
  // The app bounces to /login → Keycloak login form.
  await page.waitForURL(isKeycloakURL, { timeout: 20000 });
  await expect(page.locator('#username')).toBeVisible();
});

test.describe('with an existing SSO session', () => {
  test.use({ storageState: AUTH_USER_FILE });

  test('registry reload keeps the session (check-sso)', async ({ page }) => {
    await page.goto('/streamlits');
    await expect(page.getByRole('heading', { name: 'My apps' })).toBeVisible({
      timeout: 15000,
    });

    await page.reload();
    await expect(page.getByRole('heading', { name: 'My apps' })).toBeVisible({
      timeout: 15000,
    });
    // No Keycloak roundtrip was needed.
    expect(page.url()).toContain(STHUB_BASE_URL);
  });
});
