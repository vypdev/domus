import {describe, expect, it} from "vitest";
import {completeCoverage, coverageProblems, metrics} from "../../tooling/frontend-coverage.mjs";

function fullGroup() {
  return Object.fromEntries(metrics.map(metric => [metric, {total: 2, covered: 2, skipped: 0, pct: 100}]));
}
function fullReport() { return {total: fullGroup(), "source.ts": fullGroup()}; }

describe("complete first-party frontend coverage", () => {
  it("requires all runtime extensions, four metrics and per-file checks without exclusions", () => {
    const config = completeCoverage("owned", "reports");
    expect(config.include).toEqual(["owned/**/*.{js,mjs,cjs,jsx,ts,mts,cts,tsx}"]);
    expect(config.exclude).toBeUndefined();
    expect(config.thresholds).toEqual({lines: 100, statements: 100, functions: 100, branches: 100, perFile: true});
    expect(config.reporter).toContain("json-summary");
    expect(config.reportsDirectory).toBe("reports");
  });
  it("accepts all supported producer metrics for the exact nonempty source inventory", () => {
    expect(coverageProblems(fullReport(), ["source.ts"])).toEqual([]);
    const emptyMetric = {total: 0, covered: 0, skipped: 0, pct: 100};
    const report = fullReport();
    report.total.branches = emptyMetric;
    report["source.ts"].branches = emptyMetric;
    expect(coverageProblems(report, ["source.ts"])).toEqual([]);
  });
  it.each([null, [], "100", false])("rejects a malformed summary: %j", report => {
    expect(coverageProblems(report, ["source.ts"])).toEqual(["Coverage summary must be an object"]);
  });
  it("rejects an empty runtime inventory", () => {
    expect(coverageProblems({}, [])).toEqual(["Coverage source inventory must not be empty"]);
  });
  it("rejects omitted files and unexpected evidence", () => {
    expect(coverageProblems(fullReport(), ["unimported.ts"])).toEqual([
      "Unexpected coverage file: source.ts", "Missing coverage object: unimported.ts",
    ]);
  });
  it.each([undefined, null, []])("rejects missing or malformed aggregate evidence: %j", total => {
    expect(coverageProblems({...fullReport(), total}, ["source.ts"]))
      .toEqual(["Missing coverage object: total"]);
  });
  it.each(metrics)("rejects a missing %s metric even if the other metrics are perfect", metric => {
    const report = fullReport();
    delete report["source.ts"][metric];
    expect(coverageProblems(report, ["source.ts"]))
      .toEqual([`source.ts: incomplete ${metric} coverage`]);
  });
  it.each([
    null, [], {total: 1.5}, {total: -1}, {total: Number.MAX_SAFE_INTEGER + 1},
    {total: 2, covered: 1, skipped: 0, pct: 100},
    {total: 2, covered: 2, skipped: 1, pct: 100},
    {total: 2, covered: 2, skipped: 0, pct: 99},
  ])("rejects invalid counts or hidden gaps: %j", invalid => {
    const report = {...fullReport(), total: {...fullGroup(), lines: invalid}};
    expect(coverageProblems(report, ["source.ts"]))
      .toEqual(["total: incomplete lines coverage"]);
  });
});
