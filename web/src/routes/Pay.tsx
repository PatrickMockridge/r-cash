import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { claimLink } from "../lib/claim";
import type { SendResult } from "../lib/types";

export default function Pay() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [source, setSource] = useState("NGN");
  const [dest, setDest] = useState("KES");
  const [amount, setAmount] = useState("1");
  const [minDest, setMinDest] = useState("0");
  const [expiryBlocks, setExpiryBlocks] = useState("60");
  const [result, setResult] = useState<SendResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (status !== "unlocked") return <Unlock />;

  const send = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const parsed = Number.parseInt(expiryBlocks, 10);
      if (!Number.isSafeInteger(parsed) || parsed < 1) {
        throw new Error("expiry must be a positive number of blocks");
      }
      const response = JSON.parse(
        await client.send_transfer(source, dest, amount, minDest, BigInt(parsed)),
      ) as SendResult;
      setResult(response);
      await queryClient.invalidateQueries({ queryKey: ["balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const base = window.location.href.split("#")[0]!;
  const link = result ? claimLink(base, result.transferId, result.claimSecret) : null;

  const copy = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className="panel narrow">
      <h2>Pay</h2>
      <p className="muted">
        Send local currency with a claim link. The destination amount is escrowed on-chain;
        anyone with the secret can claim it before the expiry, and the sender can refund
        after it.
      </p>

      <div className="row gap">
        <label className="field">
          From
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="NGN">NGN</option>
            <option value="KES">KES</option>
          </select>
        </label>
        <label className="field">
          To
          <select value={dest} onChange={(event) => setDest(event.target.value)}>
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
        Minimum destination amount
        <input value={minDest} onChange={(event) => setMinDest(event.target.value)} />
      </label>
      <label className="field">
        Expiry (blocks from now)
        <input value={expiryBlocks} onChange={(event) => setExpiryBlocks(event.target.value)} />
      </label>
      {source === dest && <p className="error">Pick two different currencies.</p>}
      {error && <p className="error">{error}</p>}
      <button className="primary" onClick={send} disabled={busy || source === dest}>
        {busy ? "Sending…" : "Send"}
      </button>

      {result && link && (
        <div className="result">
          <div>
            <span className="muted">Transfer</span>
            <strong>#{result.transferId}</strong>
          </div>
          <div>
            <span className="muted">Expires at block</span>
            <span>{result.expiryHeight}</span>
          </div>
          <label className="field">
            Claim link
            <textarea readOnly value={link} rows={3} className="mono" />
          </label>
          <button className="ghost" onClick={copy}>
            {copied ? "Copied" : "Copy link"}
          </button>
          <p className="warn small">
            The secret in this link is bearer authority. Anyone who sees it can claim the
            funds. It becomes public when the claim deploy executes. Do not paste it into
            chat or email if you can share the link another way.
          </p>
        </div>
      )}
    </section>
  );
}
