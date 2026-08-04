import { test as setup } from '@playwright/test';
import { ADMIN_USER, AUTH_ADMIN_FILE, AUTH_USER_FILE, login, TEST_USER } from './helpers';

// One UI login per test run; specs then reuse the SSO session via storageState
// (the Keycloak cookies let check-sso re-authenticate silently).

setup('authenticate testuser', async ({ page }) => {
  await login(page, TEST_USER);
  await page.context().storageState({ path: AUTH_USER_FILE });
});

setup('authenticate adminuser', async ({ page }) => {
  await login(page, ADMIN_USER);
  await page.context().storageState({ path: AUTH_ADMIN_FILE });
});
