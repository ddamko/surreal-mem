import { defineConfig } from '@playwright/test';

/** Local end-to-end smoke tests against the running dev server and API (`just e2e`). */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env['DASHBOARD_URL'] ?? 'http://localhost:4200',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
});
