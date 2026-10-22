import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { VaultView } from "../lib/types";

export default function Mint() {
  const { status, client, address } = useWallet();
  const queryClient = useQueryClient();
  const [currency, setCurrency] = useState("NGN");
  const [amount, setAmount] = useState("1");
  const [revAmount, setRevAmount] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const vault = useQuery({
    queryKey: ["vault", currency, address],
    enabled: status === "unlocked" && !!client && !!address,
    queryFn: async () =>
      JSON.parse(await client!.zone_vault(currency, address!)) as VaultView,
  });

  if (status !== "unlocked") return <Unlock />;

  const run = async (action: () => Promise<string>, success: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await queryClient.invalidateQueries({ queryKey: ["vault"] });
      await queryClient.invalidateQueries({ queryKey: ["balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const open = () => run(() => client!.vault_open(currency), "Vault opened.");
  const deposit = () =>
    run(() => client!.vault_deposit(currency, amount), "Collateral deposited.");
  const withdraw = () =>
    run(() => client!.vault_withdraw(currency, amount), "Collateral withdrawn.");
  const borrow = () =>
    run(() => client!.vault_borrow(currency, amount), "Borrowed.");
  const repay = () => run(() => client!.vault_repay(currency, amount), "Repaid.");

  return (
    <div className="stack">
      <section className="panel">
        <div className="row spread">
          <div>
            <h2>Mint · {currency}</h2>
            <p className="muted small">
              Lock REV, borrow local currency. The vault is non-custodial: the Account holds
              the vault authority, and only this key can operate it.
            </p>
          </div>
          <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
            <option value="NGN">NGN</option>
            <option value="KES">KES</option>
          </select>
        </div>

        {vault.isError && <p className="error">{String(vault.error)}</p>}
        {vault.data && (
          <div className="grid">
            <div>
              <span className="muted">Collateral</span>
              <strong>{formatUnits(vault.data.collateral)} REV</strong>
            </div>
            <div>
              <span className="muted">Debt</span>
              <strong>{formatUnits(vault.data.debt)} {currency}</strong>
            </div>
            <div>
              <span className="muted">Health</span>
              <strong>{vault.data.health ? "healthy" : "below MCR"}</strong>
            </div>
            <div>
              <span className="muted">Liquidatable</span>
              <strong>{vault.data.liquidatable ? "yes" : "no"}</strong>
            </div>
            <div>
              <span className="muted">Oracle</span>
              <strong>{vault.data.fresh ? "fresh" : "stale"}</strong>
            </div>
            <div>
              <span className="muted">REV/{currency} rate</span>
              <strong>{formatUnits(vault.data.rate)}</strong>
            </div>
          </div>
        )}
        {vault.data?.liquidatable && (
          <p className="warn">
            This vault is below the minimum collateral ratio. A keeper can liquidate it
            unless collateral is added or debt is repaid.
          </p>
        )}
      </section>

      {error && <p className="error">{error}</p>}
      {message && <p className="ok">{message}</p>}

      <section className="panel">
        <h3>Fund the Account with REV</h3>
        <p className="muted small">
          Collateral is held in the Account's REV purse before the vault takes it.
        </p>
        <div className="row gap">
          <input
            aria-label="REV to deposit"
            value={revAmount}
            onChange={(event) => setRevAmount(event.target.value)}
          />
          <button
            className="ghost"
            onClick={() =>
              run(
                () => client!.deposit_rev(revAmount),
                "REV deposited into the Account.",
              )
            }
            disabled={busy}
          >
            Deposit REV
          </button>
        </div>
      </section>

      <section className="panel">
        <h3>Vault operations</h3>
        <label className="field">
          Amount ({currency} for borrow/repay, REV for collateral)
          <input value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
        <div className="row wrap gap">
          <button className="ghost" onClick={open} disabled={busy}>
            Open vault
          </button>
          <button className="ghost" onClick={deposit} disabled={busy}>
            Deposit collateral
          </button>
          <button className="ghost" onClick={withdraw} disabled={busy}>
            Withdraw collateral
          </button>
          <button className="primary" onClick={borrow} disabled={busy}>
            Borrow
          </button>
          <button className="ghost" onClick={repay} disabled={busy}>
            Repay
          </button>
        </div>
        <p className="muted small">
          Borrow and collateral withdrawal require a fresh oracle. If the feed is stale the
          protocol refuses rather than pricing a bad trade.
        </p>
      </section>
    </div>
  );
}
