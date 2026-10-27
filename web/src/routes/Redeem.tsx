import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { V4Currency, V4PsmInfo } from "../lib/types";

export default function Redeem() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [stableAmount, setStableAmount] = useState("1");
  const [minRev, setMinRev] = useState("0");
  const [revAmount, setRevAmount] = useState("1");
  const [minStable, setMinStable] = useState("0");
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

  const info = useQuery({
    queryKey: ["v4-psm", currency?.psmUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () => JSON.parse(await client!.v4_psm_info(currency!.psmUri)) as V4PsmInfo,
  });

  if (status !== "unlocked") return <Unlock />;

  const run = async (action: () => Promise<unknown>, description: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(description);
      await queryClient.invalidateQueries({ queryKey: ["v4-psm"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-totals"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>Redeem</h2>
      <p className="muted">
        The peg-stability module is the par venue. Below par, buy the stablecoin on the AMM
        and redeem it here for REV; above par, mint it here with REV and sell it on the AMM.
        Redemption is limited by the module's REV buffer, and the module may hold negative
        debt — that is how stablecoin minted from vaults is redeemed at par.
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
          <span className="muted">Signed PSM debt</span>
          <strong>{info.data ? formatUnits(info.data.stableDebt) : "—"}</strong>
        </div>
        <div>
          <span className="muted">REV buffer</span>
          <strong>{info.data ? formatUnits(info.data.revBalance) : "—"}</strong>
        </div>
        <div>
          <span className="muted">Fee</span>
          <strong>{info.data ? `${(info.data.feeBps / 100).toFixed(2)}%` : "—"}</strong>
        </div>
        <div>
          <span className="muted">Ceiling</span>
          <strong>{info.data ? formatUnits(info.data.ceiling) : "—"}</strong>
        </div>
      </div>

      <h3>Redeem stablecoin for REV</h3>
      <div className="row gap">
        <label className="field">
          Stablecoin amount
          <input
            value={stableAmount}
            onChange={(event) => setStableAmount(event.target.value)}
          />
        </label>
        <label className="field">
          Minimum REV out
          <input value={minRev} onChange={(event) => setMinRev(event.target.value)} />
        </label>
        <button
          className="primary"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () =>
                client!.v4_psm_sell(
                  currency!.psmUri,
                  currency!.code,
                  stableAmount,
                  minRev,
                ),
              "Redeemed at par minus the fee.",
            )
          }
        >
          Redeem
        </button>
      </div>

      <h3>Mint stablecoin with REV</h3>
      <div className="row gap">
        <label className="field">
          REV amount
          <input value={revAmount} onChange={(event) => setRevAmount(event.target.value)} />
        </label>
        <label className="field">
          Minimum stablecoin out
          <input value={minStable} onChange={(event) => setMinStable(event.target.value)} />
        </label>
        <button
          className="ghost"
          disabled={busy || !currency}
          onClick={() =>
            run(
              () =>
                client!.v4_psm_buy(
                  currency!.psmUri,
                  currency!.code,
                  revAmount,
                  minStable,
                ),
              "Minted at par minus the fee.",
            )
          }
        >
          Mint
        </button>
      </div>

      {message && <p className="ok">{message}</p>}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
