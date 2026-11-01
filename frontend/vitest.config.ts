import {defineConfig} from 'vitest/config';
import {playwright} from '@vitest/browser-playwright';
import {completeCoverage} from '../tooling/frontend-coverage.mjs';

export default defineConfig({optimizeDeps: {include: ['lit', 'lit/directives/live.js']}, test: {
  include: ['tests/*.test.ts'],
  browser: {enabled: true, provider: playwright(), headless: true, instances: [{browser: 'chromium'}]},
  coverage: completeCoverage('src', 'coverage'),
}});
