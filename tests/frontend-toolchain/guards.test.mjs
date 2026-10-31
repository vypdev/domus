/** Actual failing compiler/coverage executions; these fixtures never ship in Domus. */
import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {readFile, writeFile, unlink, mkdtemp, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {createConnection} from "node:net";
import {join} from "node:path";
import {fileURLToPath} from "node:url";
import {test} from "node:test";

const fixture = fileURLToPath(new URL("../fixtures/frontend-toolchain/", import.meta.url));

/** @param {number} port */
async function assertListenerClosed(port) {
  await new Promise((resolve, reject) => {
    const socket = createConnection({host: "127.0.0.1", port});
    socket.setTimeout(1_000);
    socket.once("connect", () => { socket.destroy(); reject(new Error(`Fixture listener remains on ${port}`)); });
    socket.once("timeout", () => { socket.destroy(); reject(new Error(`Listener check timed out: ${port}`)); });
    socket.once("error", error => {
      if (/** @type {NodeJS.ErrnoException} */ (error).code === "ECONNREFUSED") resolve(undefined);
      else reject(error);
    });
  });
}

/**
 * Bound and retire only this child process group, including failed browser workers.
 * @param {string[]} args
 * @param {string} cwd
 * @param {NodeJS.ProcessEnv} [env]
 */
async function run(args, cwd, env = process.env) {
  const childEnvironment = {...env};
  // A nested node --test must run its own tests, rather than inherit runner recursion state.
  delete childEnvironment.NODE_TEST_CONTEXT;
  const child = spawn(process.execPath, args, {cwd, env: childEnvironment, detached: true, stdio: ["ignore", "pipe", "pipe"]});
  let output = "";
  let timedOut = false;
  const stop = () => {
    if (child.pid !== undefined) {
      try { process.kill(-child.pid, "SIGKILL"); }
      catch (error) { if (/** @type {NodeJS.ErrnoException} */ (error).code !== "ESRCH") throw error; }
    }
  };
  const timer = setTimeout(() => { timedOut = true; stop(); }, 45_000);
  child.stdout.on("data", data => { output += data.toString(); });
  child.stderr.on("data", data => { output += data.toString(); });
  try {
    const code = await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("close", resolve);
    });
    assert.equal(timedOut, false, "Owned verification child exceeded its deadline");
    return {code, output};
  } finally { clearTimeout(timer); stop(); }
}

test("catalog declaration exception still rejects an owned story type error", async () => {
  const path = join(fixture, "stories/type-negative.stories.ts");
  await writeFile(path, "import type {Meta} from '@storybook/web-components-vite';\nconst invalid: Meta = {title: 42};\nexport default invalid;\n", {flag: "wx"});
  try {
    const result = await run(["node_modules/typescript/bin/tsc", "--noEmit", "-p", "tsconfig.catalog.json"], fixture);
    assert.notEqual(result.code, 0, result.output);
    assert.match(result.output, /type-negative\.stories\.ts.*TS2322/);
  } finally { await unlink(path); }
});

test("unimported TypeScript and JavaScript both fail the four-metric coverage gate", async () => {
  const created = [];
  const source = await readFile(join(fixture, "src/probe-toggle.ts"), "utf8");
  try {
    for (const extension of ["ts", "js"]) {
      const path = join(fixture, `src/unimported-negative.${extension}`);
      const text = extension === "ts"
        ? "export function unused(flag: boolean) { return flag ? 1 : 0; }\n"
        : "/** @param {boolean} flag */\nexport function unused(flag) { return flag ? 1 : 0; }\n";
      await writeFile(path, text, {flag: "wx"});
      created.push(path);
    }
    const result = await run(["node_modules/vitest/vitest.mjs", "run", "--coverage", "--coverage.reportsDirectory", "coverage-negative"], fixture);
    assert.notEqual(result.code, 0);
    assert.match(result.output, /Coverage for .* does not meet/);
    const report = JSON.parse(await readFile(join(fixture, "coverage-negative/coverage-summary.json"), "utf8"));
    for (const path of created) {
      for (const metric of ["lines", "statements", "functions", "branches"]) {
        assert.equal(report[path][metric].pct, 0, `${path}: ${metric}`);
      }
    }
  } finally {
    await Promise.all(created.map(path => unlink(path)));
    assert.equal(await readFile(join(fixture, "src/probe-toggle.ts"), "utf8"), source);
  }
});

test("an incomplete producer report fails the same separate evidence command", async () => {
  const root = await mkdtemp(join(tmpdir(), "domus-coverage-negative-"));
  try {
    const report = JSON.parse(await readFile(join(fixture, "coverage/coverage-summary.json"), "utf8"));
    const file = Object.keys(report).find(path => path !== "total");
    assert.ok(file);
    delete report[file].branches;
    const path = join(root, "incomplete.json");
    await writeFile(path, JSON.stringify(report));
    const result = await run(["--test", fileURLToPath(new URL("coverage-evidence.test.mjs", import.meta.url))], fixture,
      {...process.env, DOMUS_TEST_COVERAGE_FILE: path});
    assert.notEqual(result.code, 0);
    assert.match(result.output, /incomplete branches coverage/);
  } finally { await rm(root, {recursive: true}); }
});

test("Playwright releases both owned fixture servers after success and an actual test failure", async () => {
  for (const port of [56171, 56172]) await assertListenerClosed(port);
  const path = join(fixture, "e2e/teardown-negative.spec.ts");
  await writeFile(path, "import {test, expect} from '@playwright/test';\ntest('intentional teardown probe', () => { expect('actual').toBe('deliberately different'); });\n", {flag: "wx"});
  try {
    const result = await run(["node_modules/@playwright/test/cli.js", "test", "e2e/teardown-negative.spec.ts", "--reporter=line", "--output=test-results/teardown-negative"], fixture);
    assert.notEqual(result.code, 0);
    assert.match(result.output, /intentional teardown probe/);
    assert.match(result.output, /deliberately different/);
    for (const port of [56171, 56172]) await assertListenerClosed(port);
  } finally { await unlink(path); }
});
