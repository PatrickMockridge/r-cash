import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { V4Currency, V4Totals, V4Vault } from "../lib/types";

export default function Vault() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [collateral, setCollateral] = useState("1");
  const [mint, setMint] = useState("1");
  const [repay, setRepay] = useState("1");
  const [withdraw, setWithdraw] = useState("1");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const currencies = useQuery({
    queryKey: ["v4-currencies"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_currencies()) as V4Currency[],
  });

  useEffect(() => {
    if (!code && currencies.data?.length) setCode(currencies.data[0]!.code);
  }, [code, currencies.data]);

  const currency = useMemo(
    () => currencies.data?.find((entry) => entry.code === code),
    [code, currencies.data],
  );

  const vault = useQuery({
    queryKey: ["v4-vault", currency?.vaultUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () => JSON.parse(await client!.v4_vault(currency!.vaultUri)) as V4Vault,
  });

  const totals = useQuery({
    queryKey: ["v4-totals", currency?.vaultUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () => JSON.parse(await client!.v4_totals(currency!.vaultUri)) as V4Totals,
  });

  if (status !== "unlocked") return <Unlock />;

  const run = async (action: () => Promise<unknown>, description: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(description);
      await queryClient.invalidateQueries({ queryKey: ["v4-vault"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-totals"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>Vault</h2>
      <p className="muted">
        Deposit REV, mint the currency's stablecoin against it, repay with interest, or
        withdraw collateral while the position stays above the minimum collateral ratio.
      </p>

      <label className="field">
        Currency
        <select value={code} onChange={(event) => setCode(event.target.value)}>
          {(currencies.data ?? []).map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.code} — {entry.status}
            </option>
          ))}
        </select>
      </label>

      {currency && (
        <div className="grid">
          <div>
            <span className="muted">Collateral</span>
            <strong>{vault.data ? formatUnits(vault.data.collateral) : "—"}</strong>
          </div>
          <div>
            <span className="muted">Debt (accrued)</span>
            <strong>{vault.data ? formatUnits(vault.data.debt) : "—"}</strong>
          </div>
          <div>
            <span className="muted">Accrued interest</span>
            <strong>{vault.data ? formatUnits(vault.data.accruedInterest) : "—"}</strong>
          </div>
          <div>
            <span className="muted">Health</span>
            <strong>{vault.data ? (vault.data.health ? "healthy" : "liquidatable") : "—"}</strong>
          </div>
          <div>
            <span className="muted">REV / {code} rate</span>
            <strong>{vault.data ? formatUnits(vault.data.rate) : "—"}</strong>
          </div>
          <div>
            <span className="muted">Issuer paused</span>
            <strong>{totals.data ? (totals.data.paused ? "yes" : "no") : "—"}</strong>
          </div>
        </div>
      )}

      {totals.data && (
        <p className="muted small">
          supply backing: debt {formatUnits(totals.data.totalDebt)} · bad debt{" "}
          {formatUnits(totals.data.badDebt)} · sin {formatUnits(totals.data.sin)} · PSM debt{" "}
          {formatUnits(totals.data.psmDebt)}
        </p>
      )}

      <div className="row gap">
        <label className="field">
          Collateral to deposit (REV)
          <input value={collateral} onChange={(event) => setCollateral(event.target.value)} />
        </label>
        <label className="field">
          Stablecoin to mint
          <input value={mint} onChange={(event) => setMint(event.target.value)} />
        </label>
      </div>
      <div className="row gap">
        <button
          className="ghost"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () => client!.v4_vault_deposit(currency!.vaultUri, collateral),
              "Collateral deposited.",
            )
          }
        >
          Deposit
        </button>
        <button
          className="primary"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () => client!.v4_vault_mint(currency!.vaultUri, currency!.code, collateral, mint),
              "Minted into your account.",
            )
          }
        >
          Deposit and mint
        </button>
      </div>

      <div className="row gap">
        <label className="field">
          Stablecoin to repay
          <input value={repay} onChange={(event) => setRepay(event.target.value)} />
        </label>
        <label className="field">
          Collateral to withdraw (REV)
          <input value={withdraw} onChange={(event) => setWithdraw(event.target.value)} />
        </label>
      </div>
      <div className="row gap">
        <button
          className="ghost"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () => client!.v4_vault_repay(currency!.vaultUri, currency!.code, repay),
              "Repayment settled: principal burned, interest paid to the buffer and savers.",
            )
          }
        >
          Repay
        </button>
        <button
          className="ghost"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () => client!.v4_vault_withdraw(currency!.vaultUri, withdraw),
              "Collateral withdrawn.",
            )
          }
        >
          Withdraw
        </button>
      </div>

      {message && <p className="ok">{message}</p>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
