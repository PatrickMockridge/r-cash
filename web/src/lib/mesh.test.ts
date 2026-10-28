import { describe, expect, it } from "vitest";
import {
  defaultConvertPair,
  defaultPair,
  enabledCurrencies,
  MESH,
  meshPairs,
  pairKey,
  pairState,
} from "./mesh";
import type { V4Market } from "./types";

function market(base: string, quote: string, status: string): V4Market {
  return {
    marketId: `${base}/${quote}:v1`,
    slug: `${base}-${quote}-v1`,
    base,
    quote,
    version: 1,
    termsHash: "",
    status,
  };
}

describe("mesh config", () => {
  it("defaults to USD and keeps the three majors", () => {
    expect(MESH.defaultCurrency).toBe("USD");
    expect(MESH.majorCurrencies).toEqual(["USD", "EUR", "CNY"]);
  });

  it("has the launch currency set and the full unordered mesh", () => {
    expect(enabledCurrencies()).toHaveLength(16);
    expect(meshPairs()).toHaveLength((16 * 15) / 2);
  });

  it("keys pairs without orientation", () => {
    expect(pairKey("NGN", "USD")).toBe(pairKey("USD", "NGN"));
  });

  it("resolves either orientation and reports unlisted pairs", () => {
    const markets = [market("NGN", "USD", "active")];
    expect(pairState(markets, "NGN", "USD")).toBe("active");
    expect(pairState(markets, "USD", "NGN")).toBe("active");
    expect(pairState(markets, "ZAR", "USD")).toBe("unlisted");
    expect(pairState(markets, "USD", "USD")).toBe("self");
  });

  it("defaults new markets and conversions to USD", () => {
    expect(defaultPair("USD")).toEqual(["NGN", "USD"]);
    expect(defaultPair("ZAR")).toEqual(["ZAR", "USD"]);
    expect(defaultConvertPair("USD")).toEqual(["USD", "NGN"]);
    expect(defaultConvertPair("ZAR")).toEqual(["ZAR", "USD"]);
  });
});
