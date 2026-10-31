import {defineConfig} from 'vitest/config';
import {playwright} from '@vitest/browser-playwright';
import {completeCoverage} from '../../../tooling/frontend-coverage.mjs';
export default defineConfig({test: {
  include: ['unit/**/*.test.ts'],
  browser: {enabled: true, provider: playwright(), headless: true, instances: [{browser: 'chromium'}]},
  coverage: completeCoverage('src', 'coverage'),
}});
