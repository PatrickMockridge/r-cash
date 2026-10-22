// The JSON shapes the wasm facade returns. Amounts are base units.

export interface BalanceEntry {
  decimal: string;
  baseUnits: number;
}

export interface Balances {
  ownerId: string;
  amounts: Record<string, BalanceEntry>;
}

export interface PriceFeed {
  price: number;
  height: number;
  fresh: boolean;
  reason: string;
}

export interface FxRate {
  rate: number;
  fresh: boolean;
  reason: string;
}

export interface Quote {
  amountOut: number;
  fee: number;
  rate: number;
  maxIn: number;
}

export interface Reserves {
  reserveBase: number;
  reserveQuote: number;
  totalShares: number;
  rate: number;
  fresh: boolean;
  paused: boolean;
}

export interface VaultView {
  collateral: number;
  debt: number;
  health: boolean;
  liquidatable: boolean;
  fresh: boolean;
  rate: number;
}

export interface TransferInfo {
  sender: string;
  source: string;
  dest: string;
  amount: number;
  claimHash: string;
  expiry: number;
  status: "open" | "claimed" | "refunded" | string;
}

export interface ClaimResult {
  claimed: string;
  baseUnits: number;
}

export interface SendResult {
  transferId: number;
  claimSecret: string;
  claimHash: string;
  expiryHeight: number;
  claimFragment: string;
}

export interface SwapResult {
  amountOut: number;
  fee: number;
}

export const ASSETS = ["REV", "NGN", "KES", "LP:NGN/KES:fpmm"] as const;
export const CURRENCIES = ["NGN", "KES"] as const;
