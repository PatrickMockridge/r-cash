import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import { DEFAULT_ASSETS } from "../lib/types";

export default function Accounts() {
  const { status, client, address } = useWallet();
  const queryClient = useQueryClient();
  const [assetsInput, setAssetsInput] = useState(DEFAULT_ASSETS);
  const [fundAmount, setFundAmount] = useState("0.05");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const assets = assetsInput
    .split(",")
    .map((asset) => asset.trim())
    .filter(Boolean);

  // A signed balance read costs phlo, so a brand-new account with no REV cannot run one.
  // Read the native balance first (free), then enable the Account reads.
  const rev = useQuery({
    queryKey: ["rev", address],
    enabled: status === "unlocked" && !!client && !!address,
    queryFn: async () =>
      JSON.parse(await client!.rev_balance(address!)) as { baseUnits: number; rev: string },
  });

  const funded = (rev.data?.baseUnits ?? 0) > 0;

  const balances = useQuery({
    queryKey: ["v4-balances", address, assetsInput],
    enabled: status === "unlocked" && !!client && funded && assets.length > 0,
    queryFn: async () => {
      const amounts: Record<string, number> = {};
      for (const asset of assets) {
        const reply = JSON.parse(await client!.v4_balance(asset)) as { baseUnits: number };
        amounts[asset] = reply.baseUnits;
      }
      return amounts;
    },
  });

  if (status !== "unlocked") return <Unlock />;

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["rev"] });
    await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
  };

  const faucet = async () => {
    if (!client || !address) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await client.faucet(address);
      setMessage("Faucet requested 0.3 REV. It may take a block to appear.");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const fund = async () => {
    if (!client) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const reply = JSON.parse(await client.v4_fund_rev(fundAmount)) as { baseUnits: number };
      setMessage(`Deposited ${formatUnits(reply.baseUnits)} REV into the account.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const publicKey = client?.public_key() ?? "";

  return (
    <div className="stack">
      <section className="panel">
        <div className="row spread">
          <div>
            <h2>Accounts</h2>
            <p className="muted mono small">{address}</p>
          </div>
          <div className="row gap">
            <button className="ghost" onClick={faucet} disabled={busy}>
              Faucet
            </button>
            <button className="ghost" onClick={() => void refresh()} disabled={busy}>
              Refresh
            </button>
          </div>
        </div>

        {balances.isError && <p className="error">{String(balances.error)}</p>}
        {rev.isError && <p className="error">{String(rev.error)}</p>}
        {message && <p className="ok">{message}</p>}
        {error && <p className="error">{error}</p>}

        {!funded && (
          <p className="warn">
            This account has no REV yet. Use the faucet first: every signed read and every
            write costs phlo.
          </p>
        )}

        <div className="grid">
          <div>
            <span className="muted">Native REV</span>
            <strong>{formatUnits(rev.data?.baseUnits ?? 0)}</strong>
          </div>
          {assets.map((asset) => (
            <div key={asset}>
              <span className="muted">{asset} purse</span>
              <strong>{formatUnits(balances.data?.[asset] ?? 0)}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <h3>Fund the account</h3>
        <p className="muted small">
          Native REV moves into this account's REV purse. The deposit facet is the only
          receive capability; it cannot withdraw.
        </p>
        <label className="field">
          Amount (REV)
          <input value={fundAmount} onChange={(event) => setFundAmount(event.target.value)} />
        </label>
        <button className="primary" onClick={fund} disabled={busy || !funded}>
          Deposit REV
        </button>
      </section>

      <section className="panel">
        <h3>Receive address</h3>
        <p className="muted small">
          A sender needs your public key to create a claimable transfer. Your REV address
          funds native wallets; the account receives stablecoins and transfers.
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
          Asset codes (comma separated)
          <input
            value={assetsInput}
            onChange={(event) => setAssetsInput(event.target.value)}
            placeholder="REV,V4T"
          />
        </label>
      </section>
    </div>
  );
}
