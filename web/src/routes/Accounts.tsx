import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import type { Balances } from "../lib/types";

const ASSETS = "REV,NGN,KES,LP:NGN/KES:fpmm";

export default function Accounts() {
  const { status, client, address } = useWallet();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A signed balance read costs phlo, so a brand-new account with no REV cannot run one.
  // Read the native balance first (free), then enable the Account read.
  const rev = useQuery({
    queryKey: ["rev", address],
    enabled: status === "unlocked" && !!client && !!address,
    queryFn: async () =>
      JSON.parse(await client!.rev_balance(address!)) as { baseUnits: number; rev: string },
  });

  const funded = (rev.data?.baseUnits ?? 0) > 0;

  const balances = useQuery({
    queryKey: ["balances", address],
    enabled: status === "unlocked" && !!client && funded,
    queryFn: async () => JSON.parse(await client!.balances(ASSETS)) as Balances,
  });

  if (status !== "unlocked") return <Unlock />;

  const faucet = async () => {
    if (!client || !address) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await client.faucet(address);
      setMessage("Faucet requested 0.3 REV. It may take a block to appear.");
      await queryClient.invalidateQueries({ queryKey: ["rev"] });
      await queryClient.invalidateQueries({ queryKey: ["balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

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
            <button
              className="ghost"
              onClick={() => void rev.refetch()}
              disabled={balances.isFetching || rev.isFetching}
            >
              {balances.isFetching || rev.isFetching ? "Reading…" : "Refresh"}
            </button>
          </div>
        </div>

        {balances.isError && <p className="error">{String(balances.error)}</p>}
        {rev.isError && <p className="error">{String(rev.error)}</p>}
        {message && <p className="ok">{message}</p>}
        {error && <p className="error">{error}</p>}
        {!funded && status === "unlocked" && (
          <p className="warn">
            This account has no REV yet. Use the faucet: every write and every Account read
            is a deploy that pays phlo.
          </p>
        )}

        <table className="table">
          <thead>
            <tr>
              <th>Asset</th>
              <th className="right">Balance</th>
            </tr>
          </thead>
          <tbody>
            {balances.data ? (
              Object.entries(balances.data.amounts).map(([asset, entry]) => (
                <tr key={asset}>
                  <td>{asset}</td>
                  <td className="right mono">{entry.decimal}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={2} className="muted">
                  {balances.isLoading ? "Reading balances…" : "No balances yet"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="panel muted small">
        Balances are one signed deploy: the Account arm needs <code>deployerId</code>, so a
        read costs phlo and the app shows the node's finalised answer. Freshness-gated
        reads (quotes and balances) are signed for the same reason.
      </section>
    </div>
  );
}
