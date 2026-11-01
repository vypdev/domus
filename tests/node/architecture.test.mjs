import {mkdtemp, mkdir, writeFile, rm, realpath} from "node:fs/promises";
import {tmpdir} from "node:os";
import {dirname, join} from "node:path";
import {afterEach, describe, expect, it} from "vitest";
import {cruise, getAvailableTranspilers} from "dependency-cruiser";
import configuration from "../../architecture/frontend.mjs";

const ownedDirectories = [];
afterEach(async () => {
  await Promise.all(ownedDirectories.splice(0).map(path => rm(path, {recursive: true, force: true})));
});

async function check(files) {
  const root = await realpath(await mkdtemp(join(tmpdir(), "domus-architecture-")));
  ownedDirectories.push(root);
  for (const [path, source] of Object.entries(files)) {
    const target = join(root, "frontend/src", path);
    await mkdir(dirname(target), {recursive: true});
    await writeFile(target, source, "utf8");
  }
  const result = await cruise(["frontend/src"], {
    ...configuration.options, baseDir: root, ruleSet: configuration,
    validate: true, outputType: "json",
  });
  const output = typeof result.output === "string" ? JSON.parse(result.output) : result.output;
  return output.summary.violations.map(violation => violation.rule.name);
}

describe("executable frontend architecture policy", () => {
  it.each([false, true])("rejects production importing a fixture, including type-only=%s", async typeOnly => {
    const statement = typeOnly ? "import type {Fixture} from '../../tests/fixture'; export type Value = Fixture;"
      : "import {value} from '../../tests/fixture'; export const result = value;";
    expect(await check({
      "../tests/fixture.ts": "export interface Fixture { fake: true; } export const value = true;",
      "composition/main.ts": statement,
    })).toContain("production-no-test-imports");
  });
  it("checks the actual authored application graph as well as negative fixtures", async () => {
    const result = await cruise(["frontend/src"], {
      ...configuration.options, ruleSet: configuration, validate: true, outputType: "json",
    });
    const output = typeof result.output === "string" ? JSON.parse(result.output) : result.output;
    expect(output.summary.violations).toEqual([]);
    expect(output.modules.some(module => module.source === "frontend/src/domain/entry.ts")).toBe(true);
  });

  it("uses a supported TypeScript parser", () => {
    const parser = getAvailableTranspilers().find(item => item.name === "typescript");
    expect(parser?.available).toBe(true);
  });

  it("allows adapters to use application ports and application to use domain", async () => {
    expect(await check({
      "domain/model.ts": "export const value = 1;",
      "application/port.ts": "import {value} from '../domain/model.ts'; export const result = value;",
      "adapters/http.ts": "import {result} from '../application/port.ts'; export const response = result;",
      "presentation/view.ts": "import type {result} from '../application/port.ts'; export type Value = typeof result;",
    })).toEqual([]);
  });

  it.each(["domain", "application"])("rejects %s importing concrete adapters", async layer => {
    expect(await check({
      "adapters/http.ts": "export const value = 1;",
      [`${layer}/invalid.ts`]: "import {value} from '../adapters/http.ts'; export const result = value;",
    })).toContain("inner-layers-stay-pure");
  });

  it.each(["lit", "@lit/reactive-element", "home-assistant-js-websocket"])(
    "rejects an inner framework dependency on %s", async framework => {
      expect(await check({"domain/invalid.ts": `import '${framework}'; export const value = 1;`}))
        .toContain("inner-layers-no-frameworks");
    },
  );

  it("rejects a concrete transport in presentation", async () => {
    expect(await check({
      "adapters/http.ts": "export const value = 1;",
      "presentation/view.ts": "import {value} from '../adapters/http.ts'; export const view = value;",
    })).toContain("presentation-no-concrete-adapters");
  });

  it("rejects cycles within one layer", async () => {
    expect(await check({
      "domain/one.ts": "import './two.ts'; export const one = 1;",
      "domain/two.ts": "import './one.ts'; export const two = 2;",
    })).toContain("no-cycles");
  });

  it("does not let type-only imports bypass dependency direction", async () => {
    expect(await check({
      "infrastructure/dto.ts": "export interface RecordDTO { id: string; }",
      "domain/model.ts": "import type {RecordDTO} from '../infrastructure/dto.ts'; export type Model = RecordDTO;",
    })).toContain("inner-layers-stay-pure");
  });

  it("rejects unresolved imports rather than treating them as clean architecture", async () => {
    expect(await check({"domain/model.ts": "import './missing.ts'; export const value = 1;"}))
      .toContain("no-unresolved");
  });
});
