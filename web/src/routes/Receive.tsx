import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { parseClaim } from "../lib/claim";

export default function Receive() {
  const { status, address } = useWallet();
  const navigate = useNavigate();
  const [claim, setClaim] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (status !== "unlocked") return <Unlock />;

  const openClaim = () => {
    const parsed = parseClaim(claim);
    if (!parsed) {
      setError("That is not a claim link or #/claim/<id>/<secret> fragment.");
      return;
    }
    setError(null);
    navigate(`/claim/${parsed.id}/${parsed.secret}`);
  };

  return (
    <div className="stack">
      <section className="panel">
        <h2>Receive</h2>
        <p className="muted">
          Your REV address is shareable. Local currency arrives through a claim link: the
          sender escrows KES or NGN against a secret, and you claim it here.
        </p>
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
          There is no stablecoin address in v0.1: an Account's deposit facet is an
          unforgeable name, not something that can be written down or shared.
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
            placeholder="#/claim/12/…"
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
