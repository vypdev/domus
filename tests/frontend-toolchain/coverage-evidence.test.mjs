import assert from "node:assert/strict";
import {globSync, readFileSync} from "node:fs";
import {resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {test} from "node:test";
import {coverageProblems, runtimeExtensions} from "../../tooling/frontend-coverage.mjs";

const fixture = fileURLToPath(new URL("../fixtures/frontend-toolchain/", import.meta.url));

test("real Chromium coverage includes the complete fictional fixture runtime", () => {
  const files = globSync(`src/**/*.${runtimeExtensions}`, {cwd: fixture})
    .filter(path => !/\.d\.(ts|mts|cts)$/.test(path)).map(path => resolve(fixture, path));
  const path = process.env.DOMUS_TEST_COVERAGE_FILE || resolve(fixture, "coverage/coverage-summary.json");
  const report = JSON.parse(readFileSync(path, "utf8"));
  assert.deepEqual(coverageProblems(report, files), []);
});
