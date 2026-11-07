import {defineConfig} from 'vitest/config';
import {playwright} from '@vitest/browser-playwright';
import {completeCoverage} from '../tooling/frontend-coverage.mjs';

export default defineConfig({optimizeDeps: {include: [
  'lit', 'lit/directives/guard.js', 'lit/directives/keyed.js', 'lit/directives/live.js', 'lit/directives/repeat.js',
  '@vypdev/ha-ui/contracts', '@vypdev/ha-ui/tabs',
]}, test: {
  include: ['tests/*.test.ts'],
  browser: {enabled: true, provider: playwright(), headless: true, instances: [{browser: 'chromium'}]},
  coverage: completeCoverage('src', 'coverage'),
}});
