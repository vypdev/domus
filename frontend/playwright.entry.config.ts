import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e', testMatch: ['entry.spec.ts','administration.spec.ts','tasks.spec.ts','workspace-navigation.spec.ts'], forbidOnly: true, retries: 0, workers: 1,
  // All 105 native/standalone journeys plus two fixture startups and cleanup share this bounded budget.
  globalTimeout: 360_000, outputDir: 'test-results/entry-artifacts',
  reporter: [['list'], ['json', {outputFile: 'test-results/entry-results.json'}]],
  // Playwright normally disables BFCache. Exercise the real production page lifecycle instead.
  use: {headless: true, launchOptions: {ignoreDefaultArgs: ['--disable-back-forward-cache']},
    screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  webServer: (['native', 'standalone'] as const).map((mode, index) => ({
    command: `cd .. && exec uv run --frozen python tests/browser/entry_server.py --mode ${mode} --port ${56174 + index}`,
    url: `http://127.0.0.1:${56174 + index}/__fixture__/ready`,
    // Docker-owned fixtures need a chance to retire their exact container before runner exit.
    gracefulShutdown: {signal: 'SIGTERM', timeout: 5_000},
    reuseExistingServer: false, timeout: 30_000,
  })),
});
