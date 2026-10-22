import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { ClaimResult, TransferInfo } from "../lib/types";

export default function Claim() {
  const params = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { status, client } = useWallet();
  const [dest, setDest] = useState("KES");
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const id = Number.parseInt(params.id ?? "", 10);
  const secret = (params.secret ?? "").toLowerCase();
  const valid = Number.isSafeInteger(id) && id >= 0 && /^[0-9a-f]{64}$/.test(secret);

  const info = useQuery({
    queryKey: ["transfer", id],
    enabled: valid && status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.transfer_info(BigInt(id))) as TransferInfo,
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
          <h2>Transfer #{id}</h2>
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
      setResult(
        JSON.parse(await client.claim_transfer(BigInt(id), dest, secret)) as ClaimResult,
      );
      await queryClient.invalidateQueries({ queryKey: ["balances"] });
      await queryClient.invalidateQueries({ queryKey: ["transfer", id] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel narrow">
      <h2>Claim transfer #{id}</h2>
      {info.isError && <p className="error">{String(info.error)}</p>}
      {info.data && (
        <div className="result">
          <div>
            <span className="muted">Amount</span>
            <strong>
              {formatUnits(info.data.amount)} {info.data.dest}
            </strong>
          </div>
          <div>
            <span className="muted">Status</span>
            <span>{info.data.status}</span>
          </div>
          <div>
            <span className="muted">Expires at block</span>
            <span>{info.data.expiry}</span>
          </div>
          <div>
            <span className="muted">From</span>
            <span className="mono small">{info.data.sender}</span>
          </div>
        </div>
      )}

      {!result ? (
        <>
          <p className="muted small">
            Claiming deposits the escrowed amount into this wallet's Account. The secret
            becomes public in the deploy; after this, the link has no value.
          </p>
          <label className="field">
            Receive asset
            <select value={dest} onChange={(event) => setDest(event.target.value)}>
              <option value={info.data?.dest ?? "KES"}>{info.data?.dest ?? "KES"}</option>
            </select>
          </label>
          {error && <p className="error">{error}</p>}
          <button
            className="primary"
            onClick={claim}
            disabled={busy || info.data?.status !== "open"}
          >
            {busy ? "Claiming…" : "Claim"}
          </button>
          {info.data && info.data.status !== "open" && (
            <p className="error">This transfer is {info.data.status}, not open.</p>
          )}
        </>
      ) : (
        <div className="result">
          <div>
            <span className="muted">Claimed</span>
            <strong>{result.claimed}</strong>
          </div>
          <button className="primary" onClick={() => navigate("/", { replace: true })}>
            Clear the link and open Accounts
          </button>
        </div>
      )}
    </section>
  );
}
