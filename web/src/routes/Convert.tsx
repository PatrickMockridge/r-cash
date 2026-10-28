import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits, parseUnits } from "../lib/format";
import type { V4Market, V4Quote, V4Slot } from "../lib/types";
import { defaultConvertPair } from "../lib/mesh";
import { usePreferences } from "../lib/preferences";

interface Pair {
  market: V4Market;
  direction: "b2q" | "q2b";
}

export default function Convert() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const { displayCurrency } = usePreferences();
  const [initialFrom, initialTo] = defaultConvertPair(displayCurrency);
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState(initialTo);
  const [amount, setAmount] = useState("0.1");
  const [minOut, setMinOut] = useState("");
  const [slippageBps, setSlippageBps] = useState("50");
  const [quote, setQuote] = useState<V4Quote | null>(null);
  const [result, setResult] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pair = useQuery({
    queryKey: ["v4-pair", from, to],
    enabled: status === "unlocked" && !!client && from !== to,
    queryFn: async () => {
      const direct = JSON.parse(await client!.v4_market(from, to)) as V4Market | null;
      if (direct) return { market: direct, direction: "b2q" } as Pair;
      const reverse = JSON.parse(await client!.v4_market(to, from)) as V4Market | null;
      if (reverse) return { market: reverse, direction: "q2b" } as Pair;
      return null;
    },
  });

  const marketId = pair.data?.market.marketId;
  const slot = useQuery({
    queryKey: ["v4-slot", marketId],
    enabled: !!marketId && status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_slot(marketId!)) as V4Slot,
  });

  if (status !== "unlocked") return <Unlock />;

  const active = pair.data?.market.status === "active";

  const getQuote = async () => {
    if (!client || !pair.data || !slot.data) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const quoted = JSON.parse(
        await client.v4_quote(slot.data.pool, pair.data.direction, amount),
      ) as V4Quote;
      setQuote(quoted);
      const slippage = BigInt(Math.max(0, Math.min(9999, Number(slippageBps) || 0)));
      const floor = (BigInt(quoted.amountOut) * (10000n - slippage)) / 10000n;
      setMinOut(formatUnits(floor));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const execute = async () => {
    if (!client || !pair.data || !slot.data) return;
    setBusy(true);
    setError(null);
    try {
      if (parseUnits(minOut) <= 0n) {
        throw new Error("get a quote and set a non-zero minimum received");
      }
      const reply = JSON.parse(
        await client.v4_swap(slot.data.pool, pair.data.direction, from, to, amount, minOut),
      ) as { amountOut: number };
      setResult(reply.amountOut);
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
      setQuote(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel narrow">
      <h2>Convert</h2>
      <p className="muted">
        One atomic deploy: withdraw the source asset from your account, swap through the
        direct market, and deposit the destination back. The pool spread is the fee, and it
        goes to liquidity providers.
      </p>

      <div className="row gap">
        <label className="field">
          From
          <input value={from} onChange={(event) => setFrom(event.target.value.toUpperCase())} />
        </label>
        <label className="field">
          To
          <input value={to} onChange={(event) => setTo(event.target.value.toUpperCase())} />
        </label>
      </div>
      <label className="field">
        Amount
        <input value={amount} onChange={(event) => setAmount(event.target.value)} />
      </label>
      <div className="row gap">
        <label className="field">
          Slippage (bps)
          <input
            value={slippageBps}
            onChange={(event) => setSlippageBps(event.target.value)}
          />
        </label>
        <label className="field">
          Minimum received (from the quote)
          <input value={minOut} onChange={(event) => setMinOut(event.target.value)} />
        </label>
      </div>

      {pair.isError && <p className="error">{String(pair.error)}</p>}
      {pair.data === null && (
        <p className="error">No market for this pair. Check the currency mesh in Markets.</p>
      )}
      {pair.data && !active && (
        <p className="warn">
          Market {pair.data.market.marketId} is {pair.data.market.status}; a staged pool has
          no liquidity. Swap only when the market is active.
        </p>
      )}
      {pair.data && slot.data && (
        <p className="muted small mono">
          {pair.data.market.marketId} · pool {slot.data.pool}
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="row gap">
        <button
          className="ghost"
          onClick={getQuote}
          disabled={busy || !active || from === to}
        >
          {busy ? "Working…" : "Quote"}
        </button>
        <button
          className="primary"
          onClick={execute}
          disabled={busy || !active || from === to}
        >
          Convert
        </button>
      </div>

      {from === to && <p className="error">Pick two different assets.</p>}
      {quote && (
        <div className="result">
          <div>
            <span className="muted">Quoted</span>
            <strong>
              {formatUnits(quote.amountOut)} {to}
            </strong>
          </div>
          <div>
            <span className="muted">Fee (bps)</span>
            <span>{quote.fee}</span>
          </div>
          <div>
            <span className="muted">Oracle rate (1e8)</span>
            <span>{quote.rate}</span>
          </div>
          <p className="muted small">
            The quote is a signed read. Execution re-quotes; the minimum received protects
            you if the pool moved.
          </p>
        </div>
      )}
      {result !== null && (
        <div className="result">
          <div>
            <span className="muted">Converted</span>
            <strong>
              {formatUnits(result)} {to}
            </strong>
          </div>
        </div>
      )}
    </section>
  );
}
