// The wasm module is generated into ./pkg by scripts/build-wasm.mjs.
import init, { Rcash, claim_hash, node_commit, version } from "./pkg/rcash_wasm.js";

let ready: Promise<unknown> | null = null;

/** Initialise the wasm module once. */
export async function initWasm(): Promise<void> {
  if (!ready) ready = init();
  await ready;
}

export { Rcash, claim_hash, node_commit, version };
