// The wasm module is generated into ./pkg by scripts/build-wasm.mjs.
import init, { Rcash, node_commit, version } from "./pkg/rcash_wasm.js";

let ready: Promise<unknown> | null = null;

/** Initialise the wasm module once. */
export async function initWasm(): Promise<void> {
  if (!ready) ready = init();
  await ready;
}

export { Rcash, node_commit, version };
