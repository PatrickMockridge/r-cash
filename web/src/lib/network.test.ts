import { describe, expect, it } from "vitest";
import { DEVNET, TESTNET, isTestnetNode, networkForNode } from "./network";

describe("network presets", () => {
  it("selects /testnet for public endpoints", () => {
    for (const node of [
      "https://testnet.rhobot.net",
      "http://164.90.140.144:40403",
      "http://167.99.43.214:40403",
    ]) {
      expect(isTestnetNode(node)).toBe(true);
      expect(networkForNode(node)).toEqual(TESTNET);
      expect(networkForNode(node).shard).toBe("/testnet");
    }
  });

  it("keeps /root for the local devnet", () => {
    expect(isTestnetNode("http://localhost:40403")).toBe(false);
    expect(networkForNode("http://localhost:40403")).toEqual(DEVNET);
    expect(networkForNode("http://localhost:40403").shard).toBe("/root");
  });
});
