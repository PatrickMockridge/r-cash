import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Playwright owns e2e/; Vitest runs unit/component tests only.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
