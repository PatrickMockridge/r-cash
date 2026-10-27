import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { V4Lock, V4Market, V4Reserves, V4Slot } from "../lib/types";

export default function Liquidity() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [base, setBase] = useState("REV");
  const [quote, setQuote] = useState("V4T");
  const [baseAmount, setBaseAmount] = useState("1");
  const [quoteAmount, setQuoteAmount] = useState("75");
  const [lockBlocks, setLockBlocks] = useState("100");
  const [minShares, setMinShares] = useState("");
  const [minBase, setMinBase] = useState("");
  const [minQuote, setMinQuote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const market = useQuery({
    queryKey: ["v4-market-direct", base, quote],
    enabled: status === "unlocked" && !!client && base !== quote,
    queryFn: async () => JSON.parse(await client!.v4_market(base, quote)) as V4Market | null,
  });

  const marketId = market.data?.marketId;
  const slot = useQuery({
    queryKey: ["v4-slot", marketId],
    enabled: !!marketId && status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_slot(marketId!)) as V4Slot,
  });

  const reserves = useQuery({
    queryKey: ["v4-reserves", slot.data?.pool],
    enabled: !!slot.data && status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_reserves(slot.data!.pool)) as V4Reserves,
  });

  const lock = useQuery({
    queryKey: ["v4-lock", slot.data?.lock],
    enabled: !!slot.data && status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_lock_info(slot.data!.lock)) as V4Lock,
  });

  if (status !== "unlocked") return <Unlock />;

  const run = async (action: () => Promise<string>, success: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await queryClient.invalidateQueries({ queryKey: ["v4-reserves"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-lock"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const add = async () => {
    if (!client || !slot.data) return;
    setBusy(true);
    setError(null);
    try {
      const tip = JSON.parse(await client.height()) as { height: number };
      const blocks = Number.parseInt(lockBlocks, 10);
      if (!Number.isSafeInteger(blocks) || blocks < 1) {
        throw new Error("lock duration must be a positive number of blocks");
      }
      if (!minShares || minShares.trim() === "" || Number(minShares) <= 0) {
        throw new Error("set a non-zero minimum LP shares");
      }
      const reply = JSON.parse(
        await client.v4_add_liquidity(
          slot.data.pool,
          slot.data.lock,
          base,
          quote,
          baseAmount,
          quoteAmount,
          BigInt(tip.height + blocks),
          minShares,
        ),
      ) as { shares: number };
      setBusy(false);
      await run(
        async () => JSON.stringify(reply),
        `Added liquidity; ${reply.shares} shares locked.`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  };

  const release = () => {
    if (!slot.data) return;
    if (minBase.trim() === "" || minQuote.trim() === "") {
      setError("set the minimum base and quote amounts before releasing");
      return;
    }
    return run(
      () =>
        client!.v4_release_lp(
          slot.data!.lock,
          slot.data!.pool,
          base,
          quote,
          minBase,
          minQuote,
        ),
      "Released the seed LP and removed it into your account.",
    );
  };

  const active = market.data?.status === "active";

  return (
    <div className="stack">
      <section className="panel">
        <div className="row spread">
          <h2>Liquidity · {base}/{quote}</h2>
          <button
            className="ghost"
            onClick={() => {
              void reserves.refetch();
              void lock.refetch();
            }}
            disabled={reserves.isFetching}
          >
            {reserves.isFetching ? "Reading…" : "Refresh"}
          </button>
        </div>

        <div className="row gap">
          <label className="field">
            Base
            <input value={base} onChange={(event) => setBase(event.target.value.toUpperCase())} />
          </label>
          <label className="field">
            Quote
            <input value={quote} onChange={(event) => setQuote(event.target.value.toUpperCase())} />
          </label>
        </div>

        {market.isError && <p className="error">{String(market.error)}</p>}
        {market.data === null && <p className="warn">No market for this pair.</p>}
        {market.data && !active && (
          <p className="warn">
            Market {market.data.marketId} is {market.data.status}; the pool below is not a
            live corridor.
          </p>
        )}

        {reserves.data && (
          <div className="grid">
            <div>
              <span className="muted">{base} reserve</span>
              <strong>{formatUnits(reserves.data.base)}</strong>
            </div>
            <div>
              <span className="muted">{quote} reserve</span>
              <strong>{formatUnits(reserves.data.quote)}</strong>
            </div>
            <div>
              <span className="muted">Total shares</span>
              <strong>{formatUnits(reserves.data.totalShares)}</strong>
            </div>
            <div>
              <span className="muted">Seeded</span>
              <strong>{reserves.data.seeded ? "yes" : "no"}</strong>
            </div>
          </div>
        )}

        {lock.data && (
          <div className="grid">
            <div>
              <span className="muted">Seed lock</span>
              <strong>{lock.data.funded ? "funded" : "unfunded"}</strong>
            </div>
            <div>
              <span className="muted">Unlocks at height</span>
              <strong>{lock.data.untilHeight}</strong>
            </div>
            <div>
              <span className="muted">Locked shares</span>
              <strong>{formatUnits(lock.data.shares)}</strong>
            </div>
            <div>
              <span className="muted">State</span>
              <strong>
                {lock.data.released ? "released" : lock.data.cancelled ? "cancelled" : "locked"}
              </strong>
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <h3>Add liquidity and lock the seed</h3>
        <p className="muted small">
          Both sides come from your account. The LP payment is locked until the height you
          choose; activation requires a funded lock at or beyond the market's term height.
        </p>
        <div className="row gap">
          <label className="field">
            {base} amount
            <input value={baseAmount} onChange={(event) => setBaseAmount(event.target.value)} />
          </label>
          <label className="field">
            {quote} amount
            <input value={quoteAmount} onChange={(event) => setQuoteAmount(event.target.value)} />
          </label>
        </div>
        <label className="field">
          Lock for (blocks from the tip)
          <input value={lockBlocks} onChange={(event) => setLockBlocks(event.target.value)} />
        </label>
        <div className="row gap">
          <label className="field">
            Minimum LP shares
            <input value={minShares} onChange={(event) => setMinShares(event.target.value)} />
          </label>
          <label className="field">
            Minimum {base} on release
            <input value={minBase} onChange={(event) => setMinBase(event.target.value)} />
          </label>
          <label className="field">
            Minimum {quote} on release
            <input value={minQuote} onChange={(event) => setMinQuote(event.target.value)} />
          </label>
        </div>
        <p className="muted small">
          Minimums should come from the quote at a 50 bps tolerance. They are never zero in
          production: a zero minimum accepts any output.
        </p>
        {error && <p className="error">{error}</p>}
        {message && <p className="ok">{message}</p>}
        <div className="row gap">
          <button
            className="primary"
            onClick={add}
            disabled={
              busy || !slot.data || !lock.data ||
              lock.data.funded || lock.data.released || lock.data.cancelled
            }
          >
            {busy ? "Working…" : "Add and lock"}
          </button>
          <button
            className="ghost"
            onClick={release}
            disabled={busy || !slot.data || !lock.data?.funded || lock.data.released}
          >
            Release seed LP
          </button>
        </div>
      </section>
    </div>
  );
}
