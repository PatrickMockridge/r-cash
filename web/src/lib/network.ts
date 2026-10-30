// Network presets. The shard is signed into every write: the public testnet
// rejects `/root`, and devnet rejects `/testnet`. Read-only calls do not care.

export interface NetworkProfile {
  name: "devnet" | "testnet" | "custom";
  node: string;
  shard: string;
  phloLimit: number;
  phloPrice: number;
  manifestPath: string;
}

export const DEVNET: NetworkProfile = {
  name: "devnet",
  node: "http://localhost:40403",
  shard: "/root",
  phloLimit: 1_000_000,
  phloPrice: 1,
  manifestPath: "/devnet.json",
};

export const TESTNET: NetworkProfile = {
  name: "testnet",
  node: "https://testnet.rhobot.net",
  shard: "/testnet",
  phloLimit: 2_000_000,
  phloPrice: 1,
  manifestPath: "/testnet.json",
};

const TESTNET_HINTS = [
  "rhobot.net",
  "164.90.140.144",
  "167.99.43.214",
];

export function isTestnetNode(node: string): boolean {
  return TESTNET_HINTS.some((hint) => node.includes(hint));
}

export function networkForNode(node: string): NetworkProfile {
  return isTestnetNode(node) ? TESTNET : DEVNET;
}
