import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type {
  V4BufferInfo,
  V4Currency,
  V4SavingsInfo,
  V4SavingsPosition,
} from "../lib/types";
import { usePreferences } from "../lib/preferences";

export default function Earn() {
  const { status, client } = useWallet();
  const { displayCurrency } = usePreferences();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [deposit, setDeposit] = useState("1");
  const [shares, setShares] = useState("1");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const currencies = useQuery({
    queryKey: ["v4-currencies"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_currencies()) as V4Currency[],
  });
  const stablecoins = useMemo(
    () => (currencies.data ?? []).filter((entry) => entry.kind !== "external"),
    [currencies.data],
  );

  useEffect(() => {
    if (!code && stablecoins.length) {
      const first = stablecoins.find((entry) => entry.code === displayCurrency)
        ?? stablecoins[0]!;
      setCode(first.code);
    }
  }, [code, stablecoins, displayCurrency]);

  const currency = useMemo(
    () => currencies.data?.find((entry) => entry.code === code),
    [code, currencies.data],
  );

  const info = useQuery({
    queryKey: ["v4-savings", currency?.savingsUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () =>
      JSON.parse(await client!.v4_savings_info(currency!.savingsUri)) as V4SavingsInfo,
  });

  const position = useQuery({
    queryKey: ["v4-savings-position", currency?.savingsUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () =>
      JSON.parse(await client!.v4_savings_position(currency!.savingsUri)) as V4SavingsPosition,
  });

  const buffer = useQuery({
    queryKey: ["v4-buffer", currency?.bufferUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () =>
      JSON.parse(await client!.v4_buffer_info(currency!.bufferUri)) as V4BufferInfo,
  });

  if (status !== "unlocked") return <Unlock />;

  const run = async (action: () => Promise<unknown>, description: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(description);
      await queryClient.invalidateQueries({ queryKey: ["v4-savings"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-savings-position"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-buffer"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>Earn</h2>
      <p className="muted">
        Deposit the stablecoin into the savings pool and hold shares. Interest paid by
        borrowers flows into the surplus buffer and then to savers automatically on repay;
        there is no lock and no promised rate.
      </p>

      <label className="field">
        Currency
        <select value={code} onChange={(event) => setCode(event.target.value)}>
          {(currencies.data ?? []).map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.code}
            </option>
          ))}
        </select>
      </label>

      <div className="grid">
        <div>
          <span className="muted">Share value</span>
          <strong>{info.data ? formatUnits(info.data.shareValueE8) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Pool assets</span>
          <strong>{info.data ? formatUnits(info.data.totalAssets) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Your shares</span>
          <strong>{position.data ? formatUnits(position.data.shares) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Surplus buffer</span>
          <strong>{buffer.data ? formatUnits(buffer.data.surplus) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Outstanding sin</span>
          <strong>{buffer.data ? formatUnits(buffer.data.sin) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Savers' share</span>
          <strong>
            {buffer.data ? `${(buffer.data.savingsShareBps / 100).toFixed(2)}%` : "—"}
          </strong>
        </div>
      </div>

      <div className="row gap">
        <label className="field">
          Deposit amount
          <input value={deposit} onChange={(event) => setDeposit(event.target.value)} />
        </label>
        <button
          className="primary"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () => client!.v4_savings_deposit(currency!.savingsUri, currency!.code, deposit),
              "Deposited into savings.",
            )
          }
        >
          Deposit
        </button>
      </div>

      <div className="row gap">
        <label className="field">
          Shares to withdraw
          <input value={shares} onChange={(event) => setShares(event.target.value)} />
        </label>
        <button
          className="ghost"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () => client!.v4_savings_withdraw(currency!.savingsUri, currency!.code, shares),
              "Shares withdrawn into your account.",
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
