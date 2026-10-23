import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { claimLink } from "../lib/claim";
import { claim_hash } from "../wasm";
import type { V4Send } from "../lib/types";

interface Sent extends V4Send {
  secret: string;
}

export default function Pay() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [toPub, setToPub] = useState("");
  const [asset, setAsset] = useState("REV");
  const [amount, setAmount] = useState("0.01");
  const [expiryBlocks, setExpiryBlocks] = useState("60");
  const [secret, setSecret] = useState("");
  const [hash, setHash] = useState("");
  const [result, setResult] = useState<Sent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (status !== "unlocked") return <Unlock />;

  const generate = () => {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    setSecret(hex);
    setHash(claim_hash(hex));
    setResult(null);
    setError(null);
  };

  const send = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (!/^[0-9a-f]{64}$/.test(hash)) {
        throw new Error("generate a claim secret first");
      }
      const blocks = Number.parseInt(expiryBlocks, 10);
      if (!Number.isSafeInteger(blocks) || blocks < 1) {
        throw new Error("expiry must be a positive number of blocks");
      }
      const tip = JSON.parse(await client.height()) as { height: number };
      const sent = JSON.parse(
        await client.v4_send_transfer(toPub, asset, amount, hash, BigInt(tip.height + blocks)),
      ) as V4Send;
      setResult({ ...sent, secret });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const base = window.location.href.split("#")[0]!;
  const link = result ? claimLink(base, result.transfer, result.secret) : null;

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
        Send an asset with a claim link. The amount is escrowed in a per-transfer contract;
        anyone with the secret can claim it, and the sender can refund after the expiry
        height.
      </p>

      <label className="field">
        Recipient public key
        <input
          value={toPub}
          onChange={(event) => setToPub(event.target.value)}
          placeholder="04…"
          className="mono"
        />
      </label>
      <div className="row gap">
        <label className="field">
          Asset
          <input value={asset} onChange={(event) => setAsset(event.target.value)} />
        </label>
        <label className="field">
          Amount
          <input value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
      </div>
      <label className="field">
        Expiry (blocks from the tip)
        <input
          value={expiryBlocks}
          onChange={(event) => setExpiryBlocks(event.target.value)}
        />
      </label>
      <div className="row gap">
        <button className="ghost" onClick={generate}>
          {secret ? "Regenerate secret" : "Generate claim secret"}
        </button>
      </div>
      {hash && (
        <p className="muted small mono">
          claim hash {hash.slice(0, 16)}… · expiry is absolute on-chain
        </p>
      )}

      {error && <p className="error">{error}</p>}

      <button className="primary" onClick={send} disabled={busy || !secret || !toPub}>
        {busy ? "Sending…" : "Send"}
      </button>

      {result && link && (
        <div className="result">
          <div>
            <span className="muted">Transfer</span>
            <span className="mono small">{result.transfer}</span>
          </div>
          <label className="field">
            Claim link
            <div className="row gap">
              <input readOnly value={link} className="mono" />
              <button className="ghost" onClick={copy}>
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </label>
          <p className="muted small">
            The secret is in the link fragment. Keep it out of chats you do not trust: it is
            the only thing needed to claim.
          </p>
        </div>
      )}
    </section>
  );
}
