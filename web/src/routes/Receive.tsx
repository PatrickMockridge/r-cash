import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { parseClaim } from "../lib/claim";

export default function Receive() {
  const { status, client, address } = useWallet();
  const navigate = useNavigate();
  const [claim, setClaim] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (status !== "unlocked") return <Unlock />;

  const publicKey = client?.public_key() ?? "";

  const openClaim = () => {
    const parsed = parseClaim(claim);
    if (!parsed) {
      setError("That is not a claim link or #/claim/<uri>/<secret> fragment.");
      return;
    }
    setError(null);
    navigate(`/claim/${parsed.uri}/${parsed.secret}`);
  };

  return (
    <div className="stack">
      <section className="panel">
        <h2>Receive</h2>
        <p className="muted">
          Share your public key with a sender. They create a claimable transfer to your
          account, escrow the asset in a per-transfer cell, and send you the claim link. The
          link's secret is bearer authority until it is claimed.
        </p>
        <label className="field">
          Public key
          <div className="row gap">
            <input readOnly value={publicKey} className="mono" />
            <button
              className="ghost"
              onClick={() => publicKey && void navigator.clipboard.writeText(publicKey)}
            >
              Copy
            </button>
          </div>
        </label>
        <label className="field">
          REV address
          <div className="row gap">
            <input readOnly value={address ?? ""} className="mono" />
            <button
              className="ghost"
              onClick={() => address && void navigator.clipboard.writeText(address)}
            >
              Copy
            </button>
          </div>
        </label>
        <p className="muted small">
          The REV address is for native wallets and the faucet. Assets inside the account
          move by claimable transfer, not by sending to an address.
        </p>
      </section>

      <section className="panel">
        <h3>Open a claim link</h3>
        <p className="muted small">
          Paste a claim link from a sender. The secret is part of the link and is never sent
          to a server; it becomes public when the claim deploy executes.
        </p>
        <label className="field">
          Claim link or fragment
          <input
            value={claim}
            onChange={(event) => setClaim(event.target.value)}
            placeholder="#/claim/rho:id:…/…"
            className="mono"
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" onClick={openClaim}>
          Review claim
        </button>
      </section>
    </div>
  );
}
