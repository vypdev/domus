import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e', testMatch: 'entry.spec.ts', forbidOnly: true, retries: 0, workers: 1,
  globalTimeout: 180_000, outputDir: 'test-results/entry-artifacts',
  reporter: [['list'], ['json', {outputFile: 'test-results/entry-results.json'}]],
  use: {headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  webServer: (['native', 'standalone'] as const).map((mode, index) => ({
    command: `cd .. && uv run --frozen python tests/browser/entry_server.py --mode ${mode} --port ${56174 + index}`,
    url: `http://127.0.0.1:${56174 + index}/__fixture__/ready`,
    reuseExistingServer: false, timeout: 30_000,
  })),
});
