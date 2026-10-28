// The tracked mesh config is the client-side source for the supported currency
// set, the majors, the default currency and the priority pairs. Markets and
// balances are still discovered on-chain; this file only says what the product
// intends to support.

import raw from "../../../configs/mesh.json";
import type { V4Market } from "./types";

export interface MeshCurrency {
  code: string;
  name: string;
  kind: "stablecoin" | "external";
  tier: "major" | "local";
  initialPriceE8?: number;
  peg?: string;
  adapterUri?: string | null;
  enabled?: boolean;
}

export interface PriorityPair {
  base: string;
  quote: string;
}

export interface MeshConfig {
  schema: string;
  version: number;
  defaultCurrency: string;
  majorCurrencies: string[];
  currencies: MeshCurrency[];
  externalAssets: MeshCurrency[];
  priorityPairs: PriorityPair[];
}

export const MESH = raw as MeshConfig;

export function enabledCurrencies(): MeshCurrency[] {
  return [
    ...MESH.currencies,
    ...MESH.externalAssets.filter((asset) => asset.enabled === true),
  ];
}

export function currencyByCode(code: string): MeshCurrency | undefined {
  return enabledCurrencies().find((currency) => currency.code === code);
}

export function isMajor(code: string): boolean {
  return MESH.majorCurrencies.includes(code);
}

/** Unordered pair key used only by the client; the chain stores both orientations. */
export function pairKey(a: string, b: string): string {
  return [a, b].sort().join("/");
}

export function marketForPair(
  markets: V4Market[],
  base: string,
  quote: string,
): V4Market | undefined {
  const key = pairKey(base, quote);
  return markets.find((market) => pairKey(market.base, market.quote) === key);
}

export type PairState = "self" | "active" | "draft" | "paused" | "delisted" | "unlisted";

export function pairState(
  markets: V4Market[],
  base: string,
  quote: string,
): PairState {
  if (base === quote) return "self";
  const market = marketForPair(markets, base, quote);
  if (!market) return "unlisted";
  switch (market.status) {
    case "active":
    case "draft":
    case "paused":
    case "delisted":
      return market.status;
    default:
      return "unlisted";
  }
}

/** All unordered pairs among the enabled currencies. */
export function meshPairs(): Array<[string, string]> {
  const codes = enabledCurrencies().map((currency) => currency.code);
  const pairs: Array<[string, string]> = [];
  for (let i = 0; i < codes.length; i += 1) {
    for (let j = i + 1; j < codes.length; j += 1) {
      pairs.push([codes[i]!, codes[j]!]);
    }
  }
  return pairs;
}

/** The default base/quote: preferred currency against USD, or the first pair. */
export function defaultPair(preferred: string): [string, string] {
  if (preferred !== "USD" && currencyByCode(preferred)) {
    return [preferred, "USD"];
  }
  const local = enabledCurrencies().find(
    (currency) => currency.code !== "USD" && currency.tier === "local",
  );
  return local ? [local.code, "USD"] : ["USD", "EUR"];
}

/** The default convert/liquidity pair: preferred against USD, or USD against a local. */
export function defaultConvertPair(preferred: string): [string, string] {
  if (preferred !== "USD" && currencyByCode(preferred)) {
    return [preferred, "USD"];
  }
  const local = enabledCurrencies().find(
    (currency) => currency.code !== "USD" && currency.tier === "local",
  );
  return local ? ["USD", local.code] : ["USD", "EUR"];
}
