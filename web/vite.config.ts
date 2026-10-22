import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // The wasm module is emitted by wasm-pack into src/wasm/pkg.
  optimizeDeps: { exclude: ["rcash_wasm"] },
});
