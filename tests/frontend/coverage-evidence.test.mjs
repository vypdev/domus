import assert from 'node:assert/strict';
import {globSync, readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {coverageProblems, runtimeExtensions} from '../../tooling/frontend-coverage.mjs';

const frontend = fileURLToPath(new URL('../../frontend/', import.meta.url));

test('application Chromium coverage includes every authored runtime file and all four metrics', () => {
  const files = globSync(`src/**/*.${runtimeExtensions}`, {cwd: frontend})
    .filter(path => !/\.d\.(ts|mts|cts)$/.test(path)).map(path => resolve(frontend, path));
  const report = JSON.parse(readFileSync(resolve(frontend, 'coverage/coverage-summary.json'), 'utf8'));
  assert.deepEqual(coverageProblems(report, files), []);
});

test('the executed Edge.57 compatibility fixture retains its accepted source and bundle identities', () => {
  const path=resolve(frontend,'tests/fixtures/edge57-task-journal.mjs');
  const provenance=JSON.parse(readFileSync(resolve(frontend,'tests/fixtures/edge57-task-journal.provenance.json'),'utf8'));
  assert.equal(provenance.sourceCommit,'272b5e8436588b5fab090622d19298371a6dc33c');
  assert.equal(provenance.acceptedWheelSHA256,'f5a1075d1313eebc01534b8a6aba6116e27c6b15bb2ae7a5b04d31962fcc2ea0');
  const acceptedBundleSHA256='71cb56c659d28703ab9ba557c9e9ae972a88645132a601939760372aa54d0d31';
  assert.equal(provenance.bundleSHA256,acceptedBundleSHA256);
  assert.equal(createHash('sha256').update(readFileSync(path)).digest('hex'),acceptedBundleSHA256);
  assert.equal(provenance.sourceFiles.length,8);
  assert.equal(provenance.sourceFiles.find(value=>value.path==='frontend/src/adapters/task-journal.ts').sha256,
    '8b1b5a7d300c7bb12655989a3c0f58e373ceca1f32683982b82aaf7fbac63963');
  assert(!readFileSync(path,'utf8').includes('/private/tmp/'));
});
