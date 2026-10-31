/** Reusable first-party frontend coverage policy, independent of product behavior. */
export const runtimeExtensions = "{js,mjs,cjs,jsx,ts,mts,cts,tsx}";
export const metrics = /** @type {const} */ (["lines", "statements", "functions", "branches"]);

/**
 * Include unimported runtime modules and enforce every supported metric per file.
 * @param {string} sourceDirectory
 * @param {string} reportsDirectory
 * @returns {import("vitest/node").CoverageV8Options}
 */
export function completeCoverage(sourceDirectory, reportsDirectory) {
  return {
    provider: "v8",
    include: [`${sourceDirectory}/**/*.${runtimeExtensions}`],
    reporter: ["text", "json-summary", "lcov"],
    reportsDirectory,
    thresholds: {lines: 100, statements: 100, functions: 100, branches: 100, perFile: true},
  };
}

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function record(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Fail closed for absent source files, missing metrics and incomplete evidence.
 * The source inventory comes from the filesystem, independently of test imports.
 * @param {unknown} report
 * @param {readonly string[]} sourceFiles
 * @returns {string[]}
 */
export function coverageProblems(report, sourceFiles) {
  if (!record(report)) return ["Coverage summary must be an object"];
  if (sourceFiles.length === 0) return ["Coverage source inventory must not be empty"];
  const expected = new Set(["total", ...sourceFiles]);
  const problems = [];
  for (const path of Object.keys(report)) {
    if (!expected.has(path)) problems.push(`Unexpected coverage file: ${path}`);
  }
  for (const path of expected) {
    const group = report[path];
    if (!record(group)) {
      problems.push(`Missing coverage object: ${path}`);
      continue;
    }
    for (const metric of metrics) {
      const value = group[metric];
      if (!record(value) || !Number.isSafeInteger(value.total) || Number(value.total) < 0
          || value.covered !== value.total || value.skipped !== 0 || value.pct !== 100) {
        problems.push(`${path}: incomplete ${metric} coverage`);
      }
    }
  }
  return problems;
}
