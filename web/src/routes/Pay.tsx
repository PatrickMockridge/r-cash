import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { claimLink } from "../lib/claim";
import { addJournal } from "../lib/db";
import { claim_hash } from "../wasm";
import type { V4Currency, V4Send } from "../lib/types";
import { usePreferences } from "../lib/preferences";

interface Sent extends V4Send {
  secret: string;
}

export default function Pay() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const { displayCurrency } = usePreferences();
  const [toPub, setToPub] = useState("");
  const [asset, setAsset] = useState("REV");
  const [amount, setAmount] = useState("0.01");
  const [expiryBlocks, setExpiryBlocks] = useState("60");
  const [memo, setMemo] = useState("");
  const [stipend, setStipend] = useState("0");
  const [opId] = useState(() => crypto.randomUUID());
  const [secret, setSecret] = useState("");
  const [hash, setHash] = useState("");
  const [result, setResult] = useState<Sent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const currencies = useQuery({
    queryKey: ["v4-currencies"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_currencies()) as V4Currency[],
  });
  const assets = useMemo(
    () => ["REV", ...(currencies.data ?? []).map((currency) => currency.code)],
    [currencies.data],
  );

  useEffect(() => {
    if (assets.includes(displayCurrency)) setAsset(displayCurrency);
  }, [assets, displayCurrency]);

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
    const journalId = `send-${opId}`;
    try {
      if (!/^[0-9a-f]{64}$/.test(hash)) {
        throw new Error("generate a claim secret first");
      }
      if (!/^[0-9a-fA-F]+$/.test(toPub)) {
        throw new Error("recipient public key must be hex");
      }
      if (memo.length > 128) {
        throw new Error("memo is limited to 128 bytes");
      }
      const blocks = Number.parseInt(expiryBlocks, 10);
      if (!Number.isSafeInteger(blocks) || blocks < 1) {
        throw new Error("expiry must be a positive number of blocks");
      }
      const tip = JSON.parse(await client.height()) as { height: number };
      const expiry = tip.height + blocks;
      await addJournal({
        id: journalId,
        kind: "send",
        summary: `${amount} ${asset} to ${toPub.slice(0, 12)}…`,
        asset,
        amount,
        expiry,
        opId,
        recipient: toPub,
        status: "pending",
        createdAt: Date.now(),
      });
      const sent = JSON.parse(
        await client.v4_send_transfer(
          toPub,
          asset,
          amount,
          hash,
          BigInt(expiry),
          memo,
          opId,
          stipend,
        ),
      ) as V4Send;
      setResult({ ...sent, secret });
      await addJournal({
        id: journalId,
        kind: "send",
        summary: `${amount} ${asset} to ${toPub.slice(0, 12)}…`,
        transfer: sent.transfer,
        asset,
        amount,
        expiry,
        opId,
        recipient: toPub,
        status: "confirmed",
        createdAt: Date.now(),
      });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
      await queryClient.invalidateQueries({ queryKey: ["journal"] });
    } catch (cause) {
      await addJournal({
        id: journalId,
        kind: "send",
        summary: `${amount} ${asset} to ${toPub.slice(0, 12)}…`,
        asset,
        amount,
        opId,
        recipient: toPub,
        status: "failed",
        createdAt: Date.now(),
      }).catch(() => undefined);
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
        height. The transfer id is idempotent: resubmitting the same opId never double-spends.
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
          <input
            value={asset}
            onChange={(event) => setAsset(event.target.value)}
            list="pay-assets"
          />
          <datalist id="pay-assets">
            {assets.map((code) => (
              <option key={code} value={code} />
            ))}
          </datalist>
        </label>
        <label className="field">
          Amount
          <input value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
      </div>
      <label className="field">
        Expiry (blocks from the finalized tip)
        <input
          value={expiryBlocks}
          onChange={(event) => setExpiryBlocks(event.target.value)}
        />
      </label>
      <label className="field">
        Memo (optional, 128 bytes)
        <input value={memo} onChange={(event) => setMemo(event.target.value)} />
      </label>
      <label className="field">
        REV stipend for the claimer (optional, non-refundable)
        <input value={stipend} onChange={(event) => setStipend(event.target.value)} />
      </label>
      <p className="muted small">
        The stipend is sent to the recipient's REV address so they can pay the claim's phlo.
        It is not returned if the link is unused.
      </p>
      <div className="row gap">
        <button className="ghost" onClick={generate}>
          {secret ? "Regenerate secret" : "Generate claim secret"}
        </button>
      </div>
      {hash && (
        <p className="muted small mono">
          claim hash {hash.slice(0, 16)}… · opId {opId.slice(0, 8)}… · expiry is absolute
          on-chain
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
