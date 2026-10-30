import { useEffect, useState } from "react";
import { useWallet } from "../lib/store";
import { listKeystores, type StoredKeystore } from "../lib/db";
import { shortId } from "../lib/format";
import { enabledCurrencies } from "../lib/mesh";
import { DEVNET, TESTNET, type NetworkProfile } from "../lib/network";
import { usePreferences } from "../lib/preferences";

export default function Settings() {
  const { status, node, manifest, address, setNode, setManifest, lock, exportKeystore } =
    useWallet();
  const { displayCurrency, setDisplayCurrency } = usePreferences();
  const currencies = enabledCurrencies();
  const majors = currencies.filter((currency) => currency.tier === "major");
  const locals = currencies.filter((currency) => currency.tier === "local");
  const [nodeInput, setNodeInput] = useState(node);
  const [manifestInput, setManifestInput] = useState(manifest ?? "");
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState<StoredKeystore[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listKeystores().then(setSaved);
  }, [address]);

  const saveConfig = () => {
    setError(null);
    setMessage(null);
    try {
      if (nodeInput !== node) setNode(nodeInput.trim());
      setManifest(manifestInput);
      setMessage("Configuration saved. Unlock again if the node changed.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const applyPreset = async (profile: NetworkProfile) => {
    setError(null);
    setMessage(null);
    setNodeInput(profile.node);
    try {
      const response = await fetch(profile.manifestPath);
      if (!response.ok) {
        setMessage(`${profile.name}: ${profile.node} selected; paste the manifest below.`);
        return;
      }
      setManifestInput(await response.text());
      setMessage(`${profile.name}: node and manifest loaded. Save configuration.`);
    } catch (cause) {
      setMessage(`${profile.name}: node selected; manifest not served (${String(cause)}).`);
    }
  };

  const exportWallet = async () => {
    setError(null);
    setMessage(null);
    try {
      const document = await exportKeystore(password);
      const blob = new Blob([document], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = "rcash-keystore.json";
      link.click();
      URL.revokeObjectURL(url);
      setPassword("");
      setMessage("Encrypted keystore downloaded.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <h2>Settings</h2>
        <div className="row">
          <button onClick={() => void applyPreset(DEVNET)}>Use local devnet</button>
          <button onClick={() => void applyPreset(TESTNET)}>Use public testnet</button>
        </div>
        <p className="muted small">
          Public-testnet writes cost test REV and are signed with shard /testnet. The
          key stays in this browser's encrypted keystore.
        </p>
        <label className="field">
          Node public API
          <input
            value={nodeInput}
            onChange={(event) => setNodeInput(event.target.value)}
            className="mono"
          />
        </label>
        <label className="field">
          Deployment manifest
          <textarea
            value={manifestInput}
            onChange={(event) => setManifestInput(event.target.value)}
            rows={8}
            className="mono"
            placeholder="deployments/devnet.json"
          />
        </label>
        {message && <p className="ok">{message}</p>}
        {error && <p className="error">{error}</p>}
        <button className="primary" onClick={saveConfig}>
          Save configuration
        </button>
      </section>

      <section className="panel">
        <h3>Preferred currency</h3>
        <p className="muted small">
          Amounts, totals and new markets default to USD. Choose another currency for your
          own display and payment defaults; this preference is stored in this browser only.
        </p>
        <label className="field">
          Default currency
          <select
            value={displayCurrency}
            onChange={(event) => setDisplayCurrency(event.target.value)}
          >
            <optgroup label="Majors">
              {majors.map((currency) => (
                <option key={currency.code} value={currency.code}>
                  {currency.code} · {currency.name}
                </option>
              ))}
            </optgroup>
            <optgroup label="Local currencies">
              {locals.map((currency) => (
                <option key={currency.code} value={currency.code}>
                  {currency.code} · {currency.name}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
      </section>

      <section className="panel">
        <h3>Wallet</h3>
        <p className="muted small">
          {status === "unlocked" && address
            ? `Unlocked: ${address}`
            : "Locked. Unlock from any screen."}
        </p>
        <div className="row gap">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Password to export"
            autoComplete="current-password"
          />
          <button className="ghost" onClick={exportWallet} disabled={status !== "unlocked"}>
            Export keystore
          </button>
          <button className="ghost" onClick={lock} disabled={status !== "unlocked"}>
            Lock
          </button>
        </div>
      </section>

      <section className="panel">
        <h3>Saved accounts</h3>
        {saved.length === 0 ? (
          <p className="muted">No encrypted keystores in this browser.</p>
        ) : (
          <ul className="plain">
            {saved.map((entry) => (
              <li key={entry.address} className="mono small">
                {shortId(entry.address, 10)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel muted small">
        Never store a private key, mnemonic or password in localStorage, and never share a
        claim secret except through the claim link itself.
      </section>
    </div>
  );
}
