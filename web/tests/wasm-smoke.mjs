// Offline smoke test for the wasm boundary. No devnet, no network.
//
// Replaces wasm-bindgen-test, which pulled minicov and compiled C. Build first:
//   npm --prefix web run wasm:build
// Then:
//   npm --prefix web run test:wasm
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const pkgDir = resolve(webDir, "src/wasm/pkg");
const { default: init, Rcash, parity_sign, version } = await import(
  pathToFileURL(resolve(pkgDir, "rcash_wasm.js")).href
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const wasm = readFileSync(resolve(pkgDir, "rcash_wasm_bg.wasm"));
await init({ module_or_path: wasm });

assert(version() === "0.1.0", `unexpected version ${version()}`);

// The same R0a fixture the Rust test pins.
const signed = JSON.parse(parity_sign("01".repeat(32), "Nil"));
assert(
  signed.signature ===
    "3044022059126613d09aad982947545c814ee8f4bc44ced6441f70cd8d29840c2d90f78c02206b2e2b145457fd54329096b246e005b64bdaa76ffd94563ec00613bea38d6287",
  `unexpected signature ${signed.signature}`,
);
assert(
  signed.address === "1111pjC8LgoBQApxaJeuGBJWhC4rAQDbVbkSMLaXjGdfiUynCXef9",
  `unexpected address ${signed.address}`,
);

// A manifest is parsed but never contacted in this test.
const manifest = JSON.stringify({
  directory_uri: "rho:id:smoke-directory",
  account_factory_uri: "rho:id:smoke-factory",
  oracle_uri: "rho:id:smoke-oracle",
  zone_ngn_uri: "rho:id:smoke-ngn",
  zone_kes_uri: "rho:id:smoke-kes",
  components_uri: "rho:id:smoke-components",
});

const wallet = new Rcash("http://127.0.0.1:40403", manifest);
const document = wallet.create_wallet("smoke-test-password");
const address = wallet.address();
assert(address && address.startsWith("1111"), `bad address ${address}`);
assert(document.includes('"version":3'), "keystore is not v3");
assert(wallet.is_unlocked(), "wallet did not unlock");

const exported = wallet.export_keystore("second-password");
assert(exported.includes('"crypto"'), "export is not a keystore");

wallet.lock();
assert(!wallet.is_unlocked(), "lock did not clear the key");

let rejected = false;
try {
  wallet.unlock(document, "wrong-password");
} catch {
  rejected = true;
}
assert(rejected, "wrong password was accepted");

// A tampered MAC must be refused.
const tampered = document.replace('"mac":"', '"mac":"00');
rejected = false;
try {
  new Rcash("http://127.0.0.1:40403", manifest).unlock(tampered, "smoke-test-password");
} catch {
  rejected = true;
}
assert(rejected, "tampered keystore was accepted");

const unlocked = wallet.unlock(document, "smoke-test-password");
assert(unlocked === address, "unlock returned a different address");

console.log("WASM SMOKE: PASS");
