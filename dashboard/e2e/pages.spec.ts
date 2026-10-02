import { expect, test, type Page } from '@playwright/test';

const PAGES: { path: string; heading: string }[] = [
  { path: '/overview', heading: 'Memory, as the agents see it' },
  { path: '/explorer', heading: 'entities' },
  { path: '/playground', heading: 'Retrieval playground' },
  { path: '/conversations', heading: 'Conversations' },
  { path: '/analytics', heading: 'Analytics' },
  { path: '/vectors', heading: 'Vector space' },
  { path: '/curation', heading: 'Curation' },
  { path: '/operations', heading: 'Operations' },
];

async function collectErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('WebSocket')) errors.push(m.text());
  });
  return errors;
}

// The production bundle ships without a token; dev builds default to `change-me`. Use the real
// one when the environment has it (`set -a; . .env` before `just e2e`).
test.beforeEach(async ({ page }) => {
  const token = process.env['SURREALMEM_API_TOKEN'];
  if (token) await page.addInitScript((t) => localStorage.setItem('surrealmem.token', t), token);
});

for (const { path, heading } of PAGES) {
  test(`${path} renders without errors`, async ({ page }) => {
    const errors = await collectErrors(page);
    await page.goto(path);
    await expect(page.locator('main')).toContainText(heading, { timeout: 15_000 });
    await page.waitForTimeout(800);
    expect(errors).toEqual([]);
  });
}

test('retrieval playground returns a context pack', async ({ page }) => {
  await page.goto('/playground');
  await page.getByPlaceholder(/e\.g\./).fill('derek');
  await page.getByRole('button', { name: 'Retrieve' }).click();
  await expect(page.locator('main')).toContainText(/Context pack|Nothing in memory matched/, { timeout: 20_000 });
});

test('space selector scopes the overview', async ({ page }) => {
  await page.goto('/overview');
  const select = page.locator('aside select');
  await expect(select).toBeVisible();
  const options = await select.locator('option').allTextContents();
  expect(options[0]).toBe('All spaces');
});
