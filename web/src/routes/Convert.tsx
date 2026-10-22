import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { Quote, SwapResult } from "../lib/types";

export default function Convert() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [from, setFrom] = useState("NGN");
  const [to, setTo] = useState("KES");
  const [amount, setAmount] = useState("1");
  const [minOut, setMinOut] = useState("0");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [result, setResult] = useState<SwapResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status !== "unlocked") return <Unlock />;

  const getQuote = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setQuote(JSON.parse(await client.pool_quote(from, amount)) as Quote);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const execute = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    try {
      setResult(JSON.parse(await client.convert(from, to, amount, minOut)) as SwapResult);
      await queryClient.invalidateQueries({ queryKey: ["balances"] });
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
        One atomic deploy: withdraw the source currency, swap through the corridor pool, and
        deposit the destination into your Account. The pool spread is the fee, and it goes to
        liquidity providers.
      </p>

      <div className="row gap">
        <label className="field">
          From
          <select value={from} onChange={(event) => setFrom(event.target.value)}>
            <option value="NGN">NGN</option>
            <option value="KES">KES</option>
          </select>
        </label>
        <label className="field">
          To
          <select value={to} onChange={(event) => setTo(event.target.value)}>
            <option value="KES">KES</option>
            <option value="NGN">NGN</option>
          </select>
        </label>
      </div>
      <label className="field">
        Amount
        <input value={amount} onChange={(event) => setAmount(event.target.value)} />
      </label>
      <label className="field">
        Minimum received (slippage guard)
        <input value={minOut} onChange={(event) => setMinOut(event.target.value)} />
      </label>

      {error && <p className="error">{error}</p>}

      <div className="row gap">
        <button className="ghost" onClick={getQuote} disabled={busy || from === to}>
          {busy ? "Working…" : "Quote"}
        </button>
        <button className="primary" onClick={execute} disabled={busy || from === to}>
          Convert
        </button>
      </div>

      {from === to && <p className="error">Pick two different currencies.</p>}
      {quote && (
        <div className="result">
          <div>
            <span className="muted">Quoted</span>
            <strong>{formatUnits(quote.amountOut)} {to}</strong>
          </div>
          <div>
            <span className="muted">Fee (output units)</span>
            <span>{formatUnits(quote.fee)}</span>
          </div>
          <div>
            <span className="muted">Max trade</span>
            <span>{formatUnits(quote.maxIn)} {from}</span>
          </div>
          <p className="muted small">
            A quote is a separate signed read. The execution deploy re-quotes; the minimum
            received is what protects you if it moved.
          </p>
        </div>
      )}
      {result && (
        <div className="result">
          <div>
            <span className="muted">Converted</span>
            <strong>{formatUnits(result.amountOut)} {to}</strong>
          </div>
          <div>
            <span className="muted">Fee</span>
            <span>{formatUnits(result.fee)}</span>
          </div>
        </div>
      )}
    </section>
  );
}
