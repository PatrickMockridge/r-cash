import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import { addJournal } from "../lib/db";
import type { V4Transfer } from "../lib/types";

export default function Claim() {
  const params = useParams();
  const queryClient = useQueryClient();
  const { status, client } = useWallet();
  const [credited, setCredited] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uri = params.uri ?? "";
  const secret = (params.secret ?? "").toLowerCase();
  const valid = uri.startsWith("rho:id:") && /^[0-9a-f]{64}$/.test(secret);

  const info = useQuery({
    queryKey: ["v4-transfer", uri],
    enabled: valid && status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_transfer_info(uri)) as V4Transfer,
  });

  const height = useQuery({
    queryKey: ["height"],
    enabled: valid && status === "unlocked" && !!client,
    refetchInterval: 5_000,
    queryFn: async () => JSON.parse(await client!.height()) as { height: number },
  });

  if (!valid) {
    return (
      <section className="panel">
        <h2>Claim</h2>
        <p className="error">This claim link is malformed.</p>
      </section>
    );
  }

  if (status !== "unlocked") {
    return (
      <div className="stack">
        <section className="panel">
          <div className="badge">claim waiting</div>
          <h2>Transfer</h2>
          <p className="muted mono small">{uri}</p>
          <p className="muted">
            Create or unlock a wallet to receive this transfer. The secret is in the link;
            it is not stored anywhere.
          </p>
        </section>
        <Unlock />
      </div>
    );
  }

  const claim = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    try {
      const reply = JSON.parse(
        await client.v4_claim_transfer(uri, secret),
      ) as { baseUnits: number };
      setCredited(reply.baseUnits);
      await addJournal({
        id: `claim-${uri}`,
        kind: "claim",
        summary: `claimed ${formatUnits(reply.baseUnits)} into the account`,
        transfer: uri,
        status: "confirmed",
        createdAt: Date.now(),
      });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
      await queryClient.invalidateQueries({ queryKey: ["journal"] });
      await info.refetch();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const closed = info.data && info.data.status !== "open";

  return (
    <section className="panel narrow">
      <div className="badge">claim</div>
      <h2>Transfer</h2>
      <p className="muted mono small">{uri}</p>

      {info.isError && <p className="error">{String(info.error)}</p>}
      {info.data && (
        <div className="grid">
          <div>
            <span className="muted">Asset</span>
            <strong>{info.data.asset}</strong>
          </div>
          <div>
            <span className="muted">Amount</span>
            <strong>{formatUnits(info.data.amount)}</strong>
          </div>
          <div>
            <span className="muted">Expires at height</span>
            <strong>{info.data.expiry}</strong>
          </div>
          <div>
            <span className="muted">Status</span>
            <strong>{info.data.status}</strong>
          </div>
          {info.data.memo && (
            <div>
              <span className="muted">Memo</span>
              <strong>{info.data.memo}</strong>
            </div>
          )}
          {info.data.stipend > 0 && (
            <div>
              <span className="muted">REV stipend</span>
              <strong>{formatUnits(info.data.stipend)}</strong>
            </div>
          )}
          {height.data && (
            <div>
              <span className="muted">Blocks remaining</span>
              <strong>{Math.max(0, info.data.expiry - height.data.height)}</strong>
            </div>
          )}
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {credited !== null && (
        <p className="ok">
          Claimed {formatUnits(credited)} into your account.
        </p>
      )}

      <button
        className="primary"
        onClick={claim}
        disabled={busy || closed || !info.data}
      >
        {busy ? "Claiming…" : closed ? "Already closed" : "Claim into my account"}
      </button>
      <p className="muted small">
        The claim delivers the payment into this account's purse for the transfer's asset.
        A wrong secret is refused on-chain; after expiry the sender can refund instead.
      </p>
    </section>
  );
}
