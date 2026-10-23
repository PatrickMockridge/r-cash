// The JSON shapes the wasm facade returns. Amounts are base units.

export interface BalanceEntry {
  asset: string;
  baseUnits: number;
}

export interface V4Currency {
  code: string;
  stablecoinUri: string;
  vaultUri: string;
  paramsHash: string;
  status: string;
}

export interface V4Market {
  marketId: string;
  base: string;
  quote: string;
  version: number;
  termsHash: string;
  status: "draft" | "active" | "paused" | "delisted" | string;
}

export interface V4Slot {
  pool: string;
  lock: string;
}

export interface V4Reserves {
  base: number;
  quote: number;
  totalShares: number;
  seeded: boolean;
}

export interface V4Quote {
  amountOut: number;
  fee: number;
  rate: number;
}

export interface V4Transfer {
  sender: string;
  asset: string;
  amount: number;
  expiry: number;
  status: "open" | "claimed" | "refunded" | string;
}

export interface V4Send {
  id: number;
  transfer: string;
}

export interface V4Lock {
  funded: boolean;
  released: boolean;
  cancelled: boolean;
  untilHeight: number;
  shares: number;
}

export interface ClaimRef {
  uri: string;
  secret: string;
}

export const DEFAULT_ASSETS = "REV,V4T";
