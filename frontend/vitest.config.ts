import {defineConfig} from 'vitest/config';
import {playwright} from '@vitest/browser-playwright';
import {completeCoverage} from '../tooling/frontend-coverage.mjs';

export default defineConfig({optimizeDeps: {include: [
  'lit', 'lit/directives/guard.js', 'lit/directives/keyed.js', 'lit/directives/live.js', 'lit/directives/repeat.js',
  '@vypdev/ha-ui/contracts', '@vypdev/ha-ui/tabs',
  '@vypdev/ha-ui/card-contracts', '@vypdev/ha-ui/card', '@vypdev/ha-ui/button-contracts', '@vypdev/ha-ui/button',
  '@vypdev/ha-ui/feedback-contracts', '@vypdev/ha-ui/feedback',
]}, test: {
  include: ['tests/*.test.ts'],
  browser: {enabled: true, provider: playwright(), headless: true, instances: [{browser: 'chromium'}]},
  coverage: completeCoverage('src', 'coverage'),
}});
