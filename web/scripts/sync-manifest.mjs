// Copy the devnet manifest into public/ so the dev server can fetch it.
// The file is gitignored; a missing manifest is not an error (Settings accepts a paste).
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(webDir, "..");
const source = resolve(repo, "deployments/devnet.json");
if (!existsSync(source)) {
  console.log("sync-manifest: no deployments/devnet.json; use Settings to paste one");
  process.exit(0);
}
mkdirSync(resolve(webDir, "public"), { recursive: true });
copyFileSync(source, resolve(webDir, "public/devnet.json"));
console.log("sync-manifest: copied deployments/devnet.json");
