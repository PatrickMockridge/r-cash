import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { Balances, Reserves } from "../lib/types";

export default function Liquidity() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [base, setBase] = useState("1");
  const [quoteAmount, setQuoteAmount] = useState("");
  const [minShares, setMinShares] = useState("0");
  const [shares, setShares] = useState("1");
  const [minBase, setMinBase] = useState("0");
  const [minQuote, setMinQuote] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reserves = useQuery({
    queryKey: ["reserves"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () =>
      JSON.parse(await client!.pool_reserves()) as Reserves,
  });

  const lp = useQuery({
    queryKey: ["balances", "lp"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () =>
      JSON.parse(await client!.balances("LP:NGN/KES:fpmm")) as Balances,
  });

  if (status !== "unlocked") return <Unlock />;

  const run = async (action: () => Promise<string>, success: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await queryClient.invalidateQueries({ queryKey: ["balances"] });
      await queryClient.invalidateQueries({ queryKey: ["reserves"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const quote = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    try {
      const result = JSON.parse(await client.pool_quote_add(base)) as {
        base: number;
        quote: number;
      };
      setQuoteAmount(formatUnits(result.quote));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const add = () =>
    run(
      () => client!.add_liquidity(base, quoteAmount, minShares),
      "Liquidity added.",
    );
  const remove = () =>
    run(() => client!.remove_liquidity(shares, minBase, minQuote), "Liquidity removed.");

  return (
    <div className="stack">
      <section className="panel">
        <div className="row spread">
          <h2>Liquidity · NGN/KES</h2>
          <button
            className="ghost"
            onClick={() => void reserves.refetch()}
            disabled={reserves.isFetching}
          >
            {reserves.isFetching ? "Reading…" : "Refresh"}
          </button>
        </div>
        {reserves.isError && <p className="error">{String(reserves.error)}</p>}
        {reserves.data && (
          <div className="grid">
            <div>
              <span className="muted">NGN reserve</span>
              <strong>{formatUnits(reserves.data.reserveBase)}</strong>
            </div>
            <div>
              <span className="muted">KES reserve</span>
              <strong>{formatUnits(reserves.data.reserveQuote)}</strong>
            </div>
            <div>
              <span className="muted">Total shares</span>
              <strong>{formatUnits(reserves.data.totalShares)}</strong>
            </div>
            <div>
              <span className="muted">Oracle rate</span>
              <strong>{formatUnits(reserves.data.rate)}</strong>
            </div>
            <div>
              <span className="muted">Feed</span>
              <strong>{reserves.data.fresh ? "fresh" : "stale / paused"}</strong>
            </div>
            <div>
              <span className="muted">Your LP</span>
              <strong>
                {formatUnits(lp.data?.amounts["LP:NGN/KES:fpmm"]?.baseUnits ?? 0)}
              </strong>
            </div>
          </div>
        )}
      </section>

      {error && <p className="error">{error}</p>}
      {message && <p className="ok">{message}</p>}

      <section className="panel">
        <h3>Add liquidity</h3>
        <p className="muted small">
          The pool needs both sides in the oracle ratio. Quote the exact KES side first; ERTP
          cannot split or refund a payment, so the amounts must be exact.
        </p>
        <label className="field">
          NGN amount
          <input value={base} onChange={(event) => setBase(event.target.value)} />
        </label>
        <label className="field">
          KES amount
          <div className="row gap">
            <input
              value={quoteAmount}
              onChange={(event) => setQuoteAmount(event.target.value)}
            />
            <button className="ghost" onClick={quote} disabled={busy}>
              Quote
            </button>
          </div>
        </label>
        <label className="field">
          Minimum shares
          <input value={minShares} onChange={(event) => setMinShares(event.target.value)} />
        </label>
        <button className="primary" onClick={add} disabled={busy || !quoteAmount}>
          {busy ? "Working…" : "Add liquidity"}
        </button>
      </section>

      <section className="panel">
        <h3>Remove liquidity</h3>
        <label className="field">
          LP shares
          <input value={shares} onChange={(event) => setShares(event.target.value)} />
        </label>
        <div className="row gap">
          <label className="field">
            Minimum NGN
            <input value={minBase} onChange={(event) => setMinBase(event.target.value)} />
          </label>
          <label className="field">
            Minimum KES
            <input value={minQuote} onChange={(event) => setMinQuote(event.target.value)} />
          </label>
        </div>
        <button className="ghost" onClick={remove} disabled={busy}>
          {busy ? "Working…" : "Remove liquidity"}
        </button>
      </section>
    </div>
  );
}
