// The JSON shapes the wasm facade returns. Amounts are base units.

export interface BalanceEntry {
  asset: string;
  baseUnits: number;
}

export interface V4Currency {
  code: string;
  kind: "stablecoin" | "external" | string;
  stablecoinUri: string;
  custodyUri: string;
  paramsUri: string;
  vaultUri: string;
  liquidationUri: string;
  savingsUri: string;
  psmUri: string;
  bufferUri: string;
  paramsHash: string;
  sponsor: string;
  status: string;
  assetUri?: string | null;
  decimals?: number;
  chain?: string | null;
  custodian?: string | null;
}

export interface V4Market {
  marketId: string;
  slug: string;
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
  memo: string;
  opId: string;
  stipend: number;
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

export interface V4Vault {
  ownerId: string;
  collateral: number;
  debt: number;
  storedDebt: number;
  accruedInterest: number;
  lastHeight: number;
  health: boolean;
  fresh: boolean;
  rate: number;
}

export interface V4Totals {
  totalDebt: number;
  totalAccruedInterest: number;
  totalCollateral: number;
  badDebt: number;
  sin: number;
  psmDebt: number;
  paused: boolean;
  rev: number;
}

export interface V4SavingsInfo {
  totalShares: number;
  totalAssets: number;
  shareValueE8: number;
  rev: number;
}

export interface V4SavingsPosition {
  shares: number;
}

export interface V4PsmInfo {
  stableDebt: number;
  feeBps: number;
  ceiling: number;
  revBalance: number;
  rev: number;
}

export interface V4BufferInfo {
  surplus: number;
  sin: number;
  savingsShareBps: number;
  rev: number;
}

export interface V4RiskParams {
  params: Record<string, string | number | boolean>;
  genesis: Record<string, string | number | boolean>;
  paramsHash: string;
  currentHash: string;
  rev: number;
}

export interface V4Pending {
  action: string;
  argsHash: string;
  args: unknown;
  readyAt: number;
}

export interface V4Price {
  rate: number;
  fresh: boolean;
  basePrice: number;
  quotePrice: number;
  baseAge: number;
  quoteAge: number;
}

export interface V4CreatedMarket {
  marketId: string;
  pool: string;
  lock: string;
  termsHash: string;
}

export interface ClaimRef {
  uri: string;
  secret: string;
}
