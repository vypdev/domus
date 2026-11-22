import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e', testMatch: ['entry.spec.ts','administration.spec.ts','tasks.spec.ts','workspace-navigation.spec.ts','shopping-annotations.spec.ts','shopping-workspace-navigation.spec.ts'], forbidOnly: true, retries: 0, workers: 1,
  // The serial source inventory exhausted 15 minutes on self-hosted CI. Keep each
  // test/expectation deadline and zero retries; allow the whole inventory to finish.
  globalTimeout: 1_200_000, outputDir: 'test-results/entry-artifacts',
  reporter: [['list'], ['json', {outputFile: 'test-results/entry-results.json'}]],
  // Playwright normally disables BFCache. Exercise the real production page lifecycle instead.
  use: {headless: true, launchOptions: {ignoreDefaultArgs: ['--disable-back-forward-cache']},
    screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  webServer: (['native', 'standalone'] as const).map((mode, index) => ({
    command: `cd .. && mkdir -p frontend/test-results/entry-server-logs && exec uv run --frozen python tests/browser/entry_server.py --mode ${mode} --port ${56174 + index} 2>frontend/test-results/entry-server-logs/${mode}.log`,
    url: `http://127.0.0.1:${56174 + index}/__fixture__/ready`,
    // Docker-owned fixtures need a chance to retire their exact container before runner exit.
    gracefulShutdown: {signal: 'SIGTERM', timeout: 5_000},
    reuseExistingServer: false, timeout: 30_000,
  })),
});
