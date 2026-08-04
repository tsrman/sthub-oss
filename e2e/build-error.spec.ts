import { test, expect } from '@playwright/test';
import {
  cardBySlug,
  createApp,
  deleteFromRegistry,
  gotoRegistry,
  waitForStatus,
} from './helpers';

// Broken build → error status. Marked @slow: a real image build runs and fails.
test.setTimeout(300000);

test('broken requirements produce an error status @slow', async ({ page }) => {
  const slug = `e2e-err-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Err', slug);

  // Replace requirements.txt with a nonexistent package via Monaco.
  await page.getByText('requirements.txt').click();
  const editor = page.locator('.monaco-editor');
  await editor.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('definitely-not-a-real-package-xyz123');

  // Wait for autosave (save button flips back to disabled).
  const save = page.getByTestId('save-button');
  await expect(save).toBeEnabled();
  await expect(save).toBeDisabled({ timeout: 10000 });

  // Run → pip fails → the card shows «Error».
  await page.goto('/streamlits');
  const card = cardBySlug(page, slug);
  await expect(card).toBeVisible({ timeout: 20000 });
  await card.getByTestId('run-button').click();
  await waitForStatus(card, /^Error$/, 240000);

  await deleteFromRegistry(page, slug);
});
