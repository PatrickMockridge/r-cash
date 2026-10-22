import { configDefaults, defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Playwright owns e2e/; Vitest runs the unit tests only.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
