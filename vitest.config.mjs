import {defineConfig} from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/node/**/*.test.mjs"],
    coverage: {
      provider: "v8",
      include: ["architecture/**/*.mjs", "tooling/**/*.mjs"],
      reporter: ["text", "json-summary", "lcov"],
      thresholds: {100: true, perFile: true},
    },
  },
});
