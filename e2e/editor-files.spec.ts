import { test, expect } from '@playwright/test';
import { createApp, deleteFromRegistry, gotoRegistry } from './helpers';

test.setTimeout(120000);

// 1x1 transparent PNG.
const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64'
);

test('editor file operations: upload, image preview, rename, delete', async ({
  page,
}) => {
  const slug = `e2e-files-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Files', slug);

  // Upload a text file via the hidden input.
  await page.locator('input[type="file"]').setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('hello from e2e'),
  });
  await expect(page.getByText('notes.txt')).toBeVisible({ timeout: 10000 });

  // Upload an image; selecting it shows the read-only image preview.
  await page.locator('input[type="file"]').setInputFiles({
    name: 'pixel.png',
    mimeType: 'image/png',
    buffer: PNG_1PX,
  });
  const imageItem = page.getByText('pixel.png');
  await expect(imageItem).toBeVisible({ timeout: 10000 });
  await imageItem.click();
  await expect(page.locator('img[alt="pixel.png"]')).toBeVisible({ timeout: 10000 });
  await expect(page.getByText('View only')).toBeVisible();

  // Rename notes.txt → renamed.txt (✎ appears on hover; prompt dialog).
  const notesRow = page.getByText('notes.txt').locator('..');
  await notesRow.hover();
  page.once('dialog', (d) => d.accept('renamed.txt'));
  await notesRow.locator('span[title="Rename"]').click();
  await expect(page.getByText('renamed.txt')).toBeVisible({ timeout: 10000 });

  // Delete renamed.txt (native confirm dialog).
  const renamedRow = page.getByText('renamed.txt').locator('..');
  await renamedRow.hover();
  page.once('dialog', (d) => d.accept());
  await renamedRow.locator('span', { hasText: '✕' }).click();
  await expect(page.getByText('renamed.txt')).not.toBeVisible({ timeout: 10000 });

  await deleteFromRegistry(page, slug);
});

test('editor autosaves changes and lint reports problems', async ({ page }) => {
  const slug = `e2e-edit-${Date.now()}`;
  await gotoRegistry(page);
  await createApp(page, 'E2E Edit', slug);

  // app.py is open by default; append a line in Monaco.
  const editor = page.locator('.monaco-editor');
  await editor.click();
  await page.keyboard.press('Control+End');
  await page.keyboard.press('Enter');
  await page.keyboard.type('x = 1');

  // Dirty → save enabled; autosave kicks in (~1.5s) → save disabled again.
  const save = page.getByTestId('save-button');
  await expect(save).toBeEnabled();
  await expect(save).toBeDisabled({ timeout: 10000 });

  // Break the syntax on purpose and run the check.
  await editor.click();
  await page.keyboard.press('Control+End');
  await page.keyboard.press('Enter');
  await page.keyboard.type('def broken(:');
  await page.getByTestId('check-button').click();
  await expect(page.getByText('Problems')).toBeVisible();
  await expect(page.getByText('✓ Syntax is valid')).not.toBeVisible({
    timeout: 15000,
  });

  await deleteFromRegistry(page, slug);
});
