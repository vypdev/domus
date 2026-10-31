import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: 'e2e', forbidOnly: true, retries: 0, workers: 1, globalTimeout: 30_000,
  outputDir: 'test-results/artifacts',
  reporter: [['list'], ['json', {outputFile: 'test-results/browser-results.json'}]],
  use: {headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  webServer: [
    {command: 'pnpm exec vite preview --host 127.0.0.1 --port 56171 --strictPort', url: 'http://127.0.0.1:56171', reuseExistingServer: false, timeout: 10_000},
    {command: 'python3 -m http.server 56172 --bind 127.0.0.1 --directory storybook-static', url: 'http://127.0.0.1:56172', reuseExistingServer: false, timeout: 10_000},
  ],
});
