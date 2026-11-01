import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e', forbidOnly: true, retries: 0, workers: 1, globalTimeout: 90_000,
  outputDir: 'test-results/catalog-artifacts',
  reporter: [['list'], ['json', {outputFile: 'test-results/catalog-results.json'}]],
  use: {headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  webServer: {command: 'python3 -m http.server 56173 --bind 127.0.0.1 --directory storybook-static',
    url: 'http://127.0.0.1:56173', reuseExistingServer: false, timeout: 10_000},
});
