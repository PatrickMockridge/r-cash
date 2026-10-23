// Copy the devnet manifest into public/ so the dev server can fetch it.
// v0.4 manifests are preferred; the file is gitignored and a missing manifest is
// not an error (Settings accepts a paste).
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(webDir, "..");
const candidates = ["deployments/devnet-v4.json", "deployments/devnet.json"];
const source = candidates.map((path) => resolve(repo, path)).find((path) => existsSync(path));
if (!source) {
  console.log("sync-manifest: no deployment manifest; use Settings to paste one");
  process.exit(0);
}
mkdirSync(resolve(webDir, "public"), { recursive: true });
copyFileSync(source, resolve(webDir, "public/devnet.json"));
console.log(`sync-manifest: copied ${source.slice(repo.length + 1)}`);
