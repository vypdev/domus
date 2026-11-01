import assert from 'node:assert/strict';
import {globSync, readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {coverageProblems, runtimeExtensions} from '../../tooling/frontend-coverage.mjs';

const frontend = fileURLToPath(new URL('../../frontend/', import.meta.url));

test('application Chromium coverage includes every authored runtime file and all four metrics', () => {
  const files = globSync(`src/**/*.${runtimeExtensions}`, {cwd: frontend})
    .filter(path => !/\.d\.(ts|mts|cts)$/.test(path)).map(path => resolve(frontend, path));
  const report = JSON.parse(readFileSync(resolve(frontend, 'coverage/coverage-summary.json'), 'utf8'));
  assert.deepEqual(coverageProblems(report, files), []);
});
