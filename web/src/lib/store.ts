// Wallet state. The private key lives in the wasm module; this store holds only the
// unlocked client handle, the public address and non-secret configuration.

import { create } from "zustand";
import { initWasm, Rcash } from "../wasm";
import * as db from "./db";

const NODE_KEY = "rcash.node";
const MANIFEST_KEY = "rcash.manifest";
const DEFAULT_NODE =
  (import.meta.env.VITE_RCASH_NODE as string | undefined) ?? "http://localhost:40403";

interface WalletState {
  status: "idle" | "loading" | "locked" | "unlocked" | "error";
  address: string | null;
  client: Rcash | null;
  node: string;
  manifest: string | null;
  error: string | null;
  boot: () => Promise<void>;
  setNode: (node: string) => void;
  setManifest: (json: string) => void;
  createWallet: (password: string) => Promise<string>;
  unlock: (document: string, password: string) => Promise<void>;
  unlockSaved: (address: string, password: string) => Promise<void>;
  lock: () => void;
  exportKeystore: (password: string) => Promise<string>;
  clientOrThrow: () => Rcash;
}

export const useWallet = create<WalletState>((set, get) => ({
  status: "idle",
  address: null,
  client: null,
  node: localStorage.getItem(NODE_KEY) ?? DEFAULT_NODE,
  manifest: localStorage.getItem(MANIFEST_KEY),
  error: null,

  boot: async () => {
    set({ status: "loading", error: null });
    try {
      await initWasm();
      let manifest = localStorage.getItem(MANIFEST_KEY);
      if (!manifest) {
        const response = await fetch("/devnet.json");
        if (response.ok) manifest = await response.text();
      }
      if (!manifest) {
        set({
          status: "error",
          error:
            "No deployment manifest. Paste deployments/devnet.json in Settings (or run the devnet install).",
        });
        return;
      }
      // Validate the manifest by constructing a client; nothing is signed.
      new Rcash(get().node, manifest);
      localStorage.setItem(MANIFEST_KEY, manifest);
      set({ manifest, status: "locked" });
    } catch (error) {
      set({ status: "error", error: message(error) });
    }
  },

  setNode: (node) => {
    localStorage.setItem(NODE_KEY, node);
    get().lock();
    set({ node });
  },

  setManifest: (json) => {
    try {
      new Rcash(get().node, json);
    } catch (error) {
      set({ error: message(error) });
      throw error;
    }
    localStorage.setItem(MANIFEST_KEY, json);
    set({ manifest: json, error: null });
  },

  createWallet: async (password) => {
    const { node, manifest } = get();
    if (!manifest) throw new Error("no deployment manifest");
    const client = new Rcash(node, manifest);
    const document = client.create_wallet(password);
    const address = client.address();
    if (!address) throw new Error("wallet creation failed");
    await db.saveKeystore(address, document);
    set({ client, address, status: "unlocked", error: null });
    return document;
  },

  unlock: async (document, password) => {
    const { node, manifest } = get();
    if (!manifest) throw new Error("no deployment manifest");
    const client = new Rcash(node, manifest);
    const address = client.unlock(document, password);
    await db.saveKeystore(address, document);
    set({ client, address, status: "unlocked", error: null });
  },

  unlockSaved: async (address, password) => {
    const stored = await db.loadKeystore(address);
    if (!stored) throw new Error("no saved keystore for that address");
    await get().unlock(stored.document, password);
  },

  lock: () => {
    get().client?.lock();
    set({ client: null, address: null, status: "locked" });
  },

  exportKeystore: async (password) => {
    const client = get().clientOrThrow();
    return client.export_keystore(password);
  },

  clientOrThrow: () => {
    const client = get().client;
    if (!client) throw new Error("wallet is locked");
    return client;
  },
}));

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
