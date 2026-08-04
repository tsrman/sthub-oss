import { chromium } from '@playwright/test';

const baseURL = process.env.STHUB_BASE_URL ?? 'http://localhost:3001';
const browser = await chromium.launch({ headless: true });

try {
  const context = await browser.newContext({
    storageState: '.auth/user.json',
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  await page.goto(`${baseURL}/streamlits`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: /^(My|All) apps$/ }).waitFor();
  await page.screenshot({ path: '../docs/assets/dashboard.png' });

  await context.close();
} finally {
  await browser.close();
}
