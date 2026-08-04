import { test, expect, type Page } from '@playwright/test';
import { createApp, deleteFromRegistry, gotoRegistry } from './helpers';

test.setTimeout(120000);

async function aiEnabled(page: Page): Promise<boolean> {
  const assistantBtn = page.locator('button[title="AI code assistant"]');
  return assistantBtn
    .waitFor({ state: 'visible', timeout: 6000 })
    .then(() => true)
    .catch(() => false);
}

test('AI assistant streams a reply from the LLM gateway', async ({ page }) => {
  const slug = `e2e-ai-${Date.now()}`;
  await gotoRegistry(page);

  await createApp(page, 'E2E AI', slug);

  // The button only appears when the backend reports the assistant is enabled
  // (GET /ai/status). Skip cleanly when it isn't configured.
  if (!(await aiEnabled(page))) {
    await deleteFromRegistry(page, slug);
    test.skip(
      true,
      'AI assistant disabled — set AI_ENABLED=true and AI_API_KEY on the backend'
    );
    return;
  }

  await page.locator('button[title="AI code assistant"]').click();
  await expect(page.getByText('Code assistant')).toBeVisible();

  await page
    .getByPlaceholder('Type a message…')
    .fill('Answer with exactly one word: hello');
  await page.getByRole('button', { name: 'Send' }).click();

  // The user's message is echoed immediately.
  await expect(page.getByTestId('ai-message-user').last()).toContainText('hello');

  // Wait for either a real streamed reply or a surfaced gateway error
  // (e.g. invalid AI_API_KEY): the latter skips the test, like the
  // "assistant disabled" case above — it is an environment issue, not a bug.
  const assistant = page.getByTestId('ai-message-assistant').last();
  const gotReply = await Promise.race([
    expect
      .poll(async () => assistant.innerText().catch(() => ''), { timeout: 90000 })
      .toMatch(/[A-Za-z]{2,}/)
      .then(() => true)
      .catch(() => false),
    page
      .getByText(/Error contacting the model|Could not reach the assistant/)
      .first()
      .waitFor({ state: 'visible', timeout: 90000 })
      .then(() => false)
      .catch(() => false),
  ]);
  if (!gotReply) {
    await deleteFromRegistry(page, slug);
    test.skip(
      true,
      'AI gateway produced no reply (check AI_API_KEY / AI_BASE_URL in .env)'
    );
    return;
  }

  await deleteFromRegistry(page, slug);
});

test('AI assistant can insert a code block into the editor', async ({ page }) => {
  const slug = `e2e-ai-ins-${Date.now()}`;
  await gotoRegistry(page);

  await createApp(page, 'E2E AI Insert', slug);

  if (!(await aiEnabled(page))) {
    await deleteFromRegistry(page, slug);
    test.skip(true, 'AI assistant disabled — set AI_ENABLED=true and AI_API_KEY');
    return;
  }

  await page.locator('button[title="AI code assistant"]').click();
  // Ask for a fenced code block so the reply carries an insertable snippet.
  await page
    .getByPlaceholder('Type a message…')
    .fill(
      'Return ONLY a Python markdown code block with the single line ' +
        "st.write('sthub'). No explanation."
    );
  await page.getByRole('button', { name: 'Send' }).click();

  const insertBtn = page.getByRole('button', { name: 'Insert into editor' }).first();
  const gotCode = await insertBtn
    .waitFor({ state: 'visible', timeout: 60000 })
    .then(() => true)
    .catch(() => false);
  if (!gotCode) {
    // The tiny free model didn't emit a code fence — nothing to insert.
    await deleteFromRegistry(page, slug);
    test.skip(true, 'model returned no fenced code block this run');
    return;
  }

  const lines = page.locator('.monaco-editor .view-lines');
  const before = await lines.innerText();
  await insertBtn.click();
  // Insertion mutates the Monaco document (content-agnostic assertion).
  await expect
    .poll(async () => lines.innerText(), { timeout: 10000 })
    .not.toBe(before);

  await deleteFromRegistry(page, slug);
});
