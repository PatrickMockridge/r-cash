// Exact formatting for protocol base units. No JS floating-point arithmetic on money.

const BASE = 100_000_000n;

/** Format a base-unit count (decimal string or safe integer) as a decimal amount. */
export function formatUnits(value: string | number | bigint, trim = true): string {
  let raw: bigint;
  try {
    raw = BigInt(value);
  } catch {
    return String(value);
  }
  const negative = raw < 0n;
  const magnitude = negative ? -raw : raw;
  const whole = magnitude / BASE;
  const fraction = (magnitude % BASE).toString().padStart(8, "0");
  const text = trim ? fraction.replace(/0+$/, "") : fraction;
  const sign = negative ? "-" : "";
  return text ? `${sign}${whole}.${text}` : `${sign}${whole}`;
}

/** Parse a decimal string to base units, refusing more than eight fractional digits. */
export function parseUnits(value: string): bigint {
  const text = value.trim();
  if (!/^-?\d*(\.\d{0,8})?$/.test(text) || text === "" || text === ".") {
    throw new Error("amount must be a decimal with at most 8 fractional digits");
  }
  const negative = text.startsWith("-");
  const digits = negative ? text.slice(1) : text;
  const [whole = "0", fraction = ""] = digits.split(".");
  const scaled = BigInt(whole || "0") * BASE + BigInt((fraction + "00000000").slice(0, 8));
  return negative ? -scaled : scaled;
}

/** A short middle-truncated identifier. */
export function shortId(value: string, keep = 8): string {
  if (value.length <= keep * 2 + 1) return value;
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

/** Basis points as a percentage string. */
export function bps(value: number): string {
  return `${(value / 100).toFixed(2)}%`;
}
