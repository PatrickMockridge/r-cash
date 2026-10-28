import { useQuery } from "@tanstack/react-query";
import { useWallet } from "./store";

const ONE = 100_000_000n;

/**
 * Oracle rates for a set of assets in the preferred display currency.
 * A rate is 1e8-scaled quote-per-base. The read is signed and costs phlo, so
 * results are cached for a minute; a missing feed is `null`, not 1.0.
 */
export function usePrices(assets: string[], display: string) {
  const { status, client } = useWallet();
  return useQuery({
    queryKey: ["prices", assets.join(","), display],
    enabled: status === "unlocked" && !!client && assets.length > 0,
    staleTime: 60_000,
    queryFn: async () => {
      const out: Record<string, number | null> = {};
      for (const asset of assets) {
        if (asset === display) {
          out[asset] = Number(ONE);
          continue;
        }
        try {
          const price = JSON.parse(
            await client!.v4_price(asset, display, 50n),
          ) as { rate: number };
          out[asset] = price.rate;
        } catch {
          out[asset] = null;
        }
      }
      return out;
    },
  });
}

/** Convert base units of `asset` into base units of the display currency. */
export function convertPreferred(
  amount: number | bigint,
  rate: number | null | undefined,
): bigint | null {
  if (rate === null || rate === undefined) return null;
  return (BigInt(amount) * BigInt(rate)) / ONE;
}
