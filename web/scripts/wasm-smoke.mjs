// Exercise the browser wasm module against a running devnet.
// Usage: node scripts/wasm-smoke.mjs [nodeUrl]
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import init, { Rcash, version } from "../src/wasm/pkg/rcash_wasm.js";

const node = process.argv[2] ?? "http://localhost:40403";
const wasm = readFileSync(resolve("src/wasm/pkg/rcash_wasm_bg.wasm"));
const manifest = readFileSync(resolve("../deployments/devnet.json"), "utf8");
await init(wasm);

console.log("wasm version", version());
const client = new Rcash(node, manifest);

const status = JSON.parse(await client.status());
console.log("node tip", status.latestBlockNumber, "shard", status.shardId);
if (status.shardId !== "/root") throw new Error("unexpected shard");

const document = client.create_wallet("smoke-test-password");
const address = client.address();
if (!address || !address.startsWith("1111")) throw new Error("no address");
console.log("wallet", address);
if (!document.includes('"version":3')) throw new Error("not a v3 keystore");

await client.faucet(address);
let balance = { baseUnits: 0, rev: "0" };
for (let attempt = 0; attempt < 15; attempt += 1) {
  await new Promise((r) => setTimeout(r, 2000));
  balance = JSON.parse(await client.rev_balance(address));
  if (Number(balance.baseUnits) > 0) break;
}
console.log("REV balance", balance.rev);
if (Number(balance.baseUnits) <= 0) throw new Error("faucet did not fund the address");

client.lock();
if (client.is_unlocked()) throw new Error("lock did not clear the key");
let rejected = false;
try {
  client.unlock(document, "wrong-password");
} catch {
  rejected = true;
}
if (!rejected) throw new Error("wrong password was accepted");
const unlocked = client.unlock(document, "smoke-test-password");
if (unlocked !== address) throw new Error("unlock returned a different address");
console.log("keystore round-trip ok");

const next = JSON.parse(await client.transfer_next_id());
console.log("transfer nextId", next.nextId);
console.log("WASM SMOKE: PASS");
