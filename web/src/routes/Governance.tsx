import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import type { V4Currency, V4Pending, V4RiskParams } from "../lib/types";

export default function Governance() {
  const { status, client } = useWallet();
  const [code, setCode] = useState("");
  const [domain, setDomain] = useState("");
  const [nonce, setNonce] = useState("0");

  const currencies = useQuery({
    queryKey: ["v4-currencies"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_currencies()) as V4Currency[],
  });

  useEffect(() => {
    if (!code && currencies.data?.length) {
      const first = currencies.data[0]!;
      setCode(first.code);
      setDomain(`stablecoin:${first.code}`);
    }
  }, [code, currencies.data]);

  const currency = useMemo(
    () => currencies.data?.find((entry) => entry.code === code),
    [code, currencies.data],
  );

  const risk = useQuery({
    queryKey: ["v4-risk", currency?.paramsUri],
    enabled: status === "unlocked" && !!client && !!currency,
    queryFn: async () =>
      JSON.parse(await client!.v4_risk_params(currency!.paramsUri)) as V4RiskParams,
  });

  const pending = useQuery({
    queryKey: ["v4-pending", domain, nonce],
    enabled: status === "unlocked" && !!client && domain.length > 0,
    queryFn: async () =>
      JSON.parse(await client!.v4_pending(domain, BigInt(nonce || "0"))) as V4Pending | null,
  });

  if (status !== "unlocked") return <Unlock />;

  return (
    <section className="panel">
      <h2>Governance</h2>
      <p className="muted">
        Read-only view. Admin actions and timelocked parameter changes are submitted with the
        CLI, which signs the 2-of-3 intent. Risk, savings-share and PSM policy changes execute
        after the 100-block timelock; currency pause and market status are immediate.
      </p>

      <label className="field">
        Currency
        <select
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
            setDomain(`stablecoin:${event.target.value}`);
          }}
        >
          {(currencies.data ?? []).map((entry) => (
            <option key={entry.code} value={entry.code}>
              {entry.code}
            </option>
          ))}
        </select>
      </label>

      {risk.data && (
        <div className="grid">
          <div>
            <span className="muted">Genesis params hash</span>
            <span className="mono small">{risk.data.paramsHash.slice(0, 20)}…</span>
          </div>
          <div>
            <span className="muted">Current params hash</span>
            <span className="mono small">{risk.data.currentHash.slice(0, 20)}…</span>
          </div>
          <div>
            <span className="muted">MCR</span>
            <strong>{String(risk.data.params.mcrBps ?? "—")} bps</strong>
          </div>
          <div>
            <span className="muted">Rate per block</span>
            <strong>{String(risk.data.params.ratePerBlock ?? "—")}</strong>
          </div>
          <div>
            <span className="muted">Savers' share</span>
            <strong>{String(risk.data.params.savingsShareBps ?? "—")} bps</strong>
          </div>
          <div>
            <span className="muted">PSM fee</span>
            <strong>{String(risk.data.params.psmFeeBps ?? "—")} bps</strong>
          </div>
        </div>
      )}

      <h3>Scheduled action</h3>
      <div className="row gap">
        <label className="field">
          Domain
          <input value={domain} onChange={(event) => setDomain(event.target.value)} />
        </label>
        <label className="field">
          Nonce
          <input value={nonce} onChange={(event) => setNonce(event.target.value)} />
        </label>
      </div>
      {pending.data ? (
        <div className="grid">
          <div>
            <span className="muted">Action</span>
            <strong>{pending.data.action}</strong>
          </div>
          <div>
            <span className="muted">Args hash</span>
            <span className="mono small">{pending.data.argsHash.slice(0, 20)}…</span>
          </div>
          <div>
            <span className="muted">Ready at height</span>
            <strong>{pending.data.readyAt}</strong>
          </div>
        </div>
      ) : (
        <p className="muted small">No action scheduled for this domain and nonce.</p>
      )}
    </section>
  );
}
