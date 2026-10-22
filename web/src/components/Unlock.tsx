import { useEffect, useState } from "react";
import { useWallet } from "../lib/store";
import { listKeystores, type StoredKeystore } from "../lib/db";

type Mode = "saved" | "create" | "import";

export default function Unlock() {
  const { status, error, createWallet, unlock, unlockSaved } = useWallet();
  const [mode, setMode] = useState<Mode>("saved");
  const [saved, setSaved] = useState<StoredKeystore[]>([]);
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [document, setDocument] = useState("");
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    void listKeystores().then((entries) => {
      setSaved(entries);
      if (entries[0]) setAddress(entries[0].address);
      if (entries.length === 0) setMode("create");
    });
  }, []);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setLocalError(null);
    try {
      if (mode === "saved") {
        await unlockSaved(address, password);
      } else if (mode === "import") {
        await unlock(document, password);
      } else {
        if (password.length < 8) throw new Error("use at least 8 characters");
        if (password !== confirm) throw new Error("passwords do not match");
        const keystore = await createWallet(password);
        download(keystore);
      }
      setPassword("");
      setConfirm("");
      setDocument("");
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel narrow">
      <h2>Wallet</h2>
      <p className="muted">
        The key is generated and encrypted inside the WebAssembly module. Only the encrypted
        keystore is stored in this browser.
      </p>
      {error && <p className="error">{error}</p>}
      {localError && <p className="error">{localError}</p>}
      {status === "loading" && <p className="muted">Loading the client…</p>}

      <div className="segmented">
        <button
          type="button"
          className={mode === "saved" ? "seg active" : "seg"}
          onClick={() => setMode("saved")}
          disabled={saved.length === 0}
        >
          Unlock
        </button>
        <button
          type="button"
          className={mode === "create" ? "seg active" : "seg"}
          onClick={() => setMode("create")}
        >
          Create
        </button>
        <button
          type="button"
          className={mode === "import" ? "seg active" : "seg"}
          onClick={() => setMode("import")}
        >
          Import
        </button>
      </div>

      <form onSubmit={onSubmit} className="form">
        {mode === "saved" && (
          <label>
            Account
            <select value={address} onChange={(event) => setAddress(event.target.value)}>
              {saved.map((entry) => (
                <option key={entry.address} value={entry.address}>
                  {entry.address}
                </option>
              ))}
            </select>
          </label>
        )}
        {mode === "import" && (
          <label>
            Keystore JSON
            <textarea
              value={document}
              onChange={(event) => setDocument(event.target.value)}
              rows={5}
              placeholder='{"version":3,...}'
            />
          </label>
        )}
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === "create" ? "new-password" : "current-password"}
          />
        </label>
        {mode === "create" && (
          <label>
            Confirm password
            <input
              type="password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              autoComplete="new-password"
            />
          </label>
        )}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Working…" : mode === "create" ? "Create wallet" : "Unlock"}
        </button>
        {mode === "create" && (
          <p className="muted small">
            Creating downloads a backup of the encrypted keystore. Keep it; losing it loses
            the account.
          </p>
        )}
      </form>
    </div>
  );
}

function download(document: string) {
  const blob = new Blob([document], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = "rcash-keystore.json";
  link.click();
  URL.revokeObjectURL(url);
}
