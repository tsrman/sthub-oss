import { test, expect } from '@playwright/test';
import { isKeycloakURL, STHUB_BASE_URL } from './helpers';

// Explicit UI login flow — needs a fresh, unauthenticated context.
test.use({ storageState: { cookies: [], origins: [] } });

test('login via Keycloak and open registry', async ({ page }) => {
  // The root page now uses check-sso and falls back to /login,
  // so go directly to /login to trigger the Keycloak redirect.
  await page.goto('/login');

  // Wait for Keycloak login page.
  await page.waitForURL(isKeycloakURL, { timeout: 15000 });

  await page.fill('#username', 'testuser');
  await page.fill('#password', 'testpass');
  await page.click('#kc-login');

  // After successful login we should end up on the registry page.
  await page.waitForURL(`${STHUB_BASE_URL}/streamlits`, { timeout: 20000 });
  await expect(page.getByRole('heading', { name: 'My apps' })).toBeVisible({ timeout: 10000 });
});
