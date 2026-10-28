import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { formatUnits } from "../lib/format";
import type { V4CreatedMarket, V4Market, V4Price } from "../lib/types";
import {
  defaultPair,
  enabledCurrencies,
  MESH,
  meshPairs,
  pairState,
} from "../lib/mesh";
import { usePreferences } from "../lib/preferences";

function template(base: string, quote: string): string {
  return `{
  "market_id": "${base}/${quote}:v1",
  "slug": "${base.toLowerCase()}-${quote.toLowerCase()}-v1",
  "base": "${base}",
  "quote": "${quote}",
  "version": 1,
  "sponsor_pub_key": "",
  "sponsor_owner_id": "",
  "base_feed_policy_hash": "",
  "quote_feed_policy_hash": "",
  "base_spread_bps": 20,
  "skew_spread_bps": 80,
  "max_trade_bps": 500,
  "min_liquidity": 100000000,
  "first_deposit_tolerance_bps": 100,
  "depth_floor_quote": 1,
  "min_ticket_quote": 1,
  "seed_base": 1,
  "seed_quote": 1,
  "seed_initial_shares": 1,
  "lock_beneficiary_pub_key": "",
  "lock_min_blocks": 10,
  "lock_until_height": 100,
  "book_default_expiry_blocks": 720,
  "book_max_expiry_blocks": 129600,
  "max_pair_age_blocks": 50
}`;
}

export default function Markets() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const { displayCurrency } = usePreferences();
  const [initialBase, initialQuote] = defaultPair(displayCurrency);
  const [terms, setTerms] = useState(() => template(initialBase, initialQuote));
  const [created, setCreated] = useState<V4CreatedMarket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [base, setBase] = useState(initialBase);
  const [quote, setQuote] = useState(initialQuote);

  const markets = useQuery({
    queryKey: ["v4-markets"],
    enabled: status === "unlocked" && !!client,
    queryFn: async () => JSON.parse(await client!.v4_markets()) as V4Market[],
  });

  useEffect(() => {
    if (!base || !quote) {
      const [nextBase, nextQuote] = defaultPair(displayCurrency);
      setBase(nextBase);
      setQuote(nextQuote);
    }
  }, [base, quote, displayCurrency]);

  const currencies = enabledCurrencies();
  const marketsNow = markets.data ?? [];
  const activePairs = meshPairs().filter(
    ([a, b]) => pairState(marketsNow, a, b) === "active",
  ).length;

  const price = useQuery({
    queryKey: ["v4-price", base, quote],
    enabled: status === "unlocked" && !!client && base.length > 0 && quote.length > 0,
    queryFn: async () =>
      JSON.parse(await client!.v4_price(base, quote, 50n)) as V4Price,
  });

  if (status !== "unlocked") return <Unlock />;

  const create = async () => {
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      JSON.parse(terms);
      const result = JSON.parse(await client!.v4_create_market(terms)) as V4CreatedMarket;
      setCreated(result);
      await queryClient.invalidateQueries({ queryKey: ["v4-markets"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>Markets</h2>
      <p className="muted">
        Direct pairs only; USD is the default quote. A market is created as a draft, seeded
        through Liquidity, then activated. Swaps happen on Convert.{" "}
        {activePairs} of {meshPairs().length} supported pairs are active.
      </p>

      <h3>Currency mesh</h3>
      <p className="muted small">
        Supported pairs from <code>configs/mesh.json</code>. <strong>Unlisted</strong> pairs
        have no market yet; select one to prefill the create form, then seed and activate it.
      </p>
      <div className="mesh-wrap">
        <table className="table mesh">
          <thead>
            <tr>
              <th />
              {currencies.map((currency) => (
                <th key={currency.code} className="mono small">
                  {currency.code}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currencies.map((row) => (
              <tr key={row.code}>
                <th className="mono small">{row.code}</th>
                {currencies.map((column) => {
                  const state = pairState(marketsNow, row.code, column.code);
                  return (
                    <td key={column.code} className={`mesh-${state}`}>
                      {state === "self" ? (
                        "—"
                      ) : (
                        <button
                          className="mesh-cell"
                          title={`${row.code}/${column.code}: ${state}`}
                          onClick={() => {
                            setBase(row.code);
                            setQuote(column.code);
                            setTerms(template(row.code, column.code));
                          }}
                        >
                          {state}
                        </button>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Majors: {MESH.majorCurrencies.join(", ")}. Default display: {MESH.defaultCurrency}.
      </p>

      <table className="table">
        <thead>
          <tr>
            <th>Market</th>
            <th>Pair</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(markets.data ?? []).map((market) => (
            <tr key={market.marketId}>
              <td className="mono small">{market.slug || market.marketId}</td>
              <td>
                {market.base}/{market.quote}
              </td>
              <td>{market.status}</td>
              <td>
                {market.status === "active" && (
                  <Link className="ghost" to="/convert">
                    Convert
                  </Link>
                )}
                {market.status === "draft" && (
                  <Link className="ghost" to="/liquidity">
                    Seed
                  </Link>
                )}
              </td>
            </tr>
          ))}
          {markets.data?.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No markets yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3>Oracle</h3>
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
      {price.data ? (
        <div className="grid">
          <div>
            <span className="muted">Rate (quote per base)</span>
            <strong>{formatUnits(price.data.rate)}</strong>
          </div>
          <div>
            <span className="muted">Fresh</span>
            <strong>{price.data.fresh ? "yes" : "no"}</strong>
          </div>
          <div>
            <span className="muted">{base} age (blocks)</span>
            <strong>{price.data.baseAge}</strong>
          </div>
          <div>
            <span className="muted">{quote} age (blocks)</span>
            <strong>{price.data.quoteAge}</strong>
          </div>
        </div>
      ) : (
        <p className="muted small">Enter a listed pair to read the hub rate and feed ages.</p>
      )}
      {price.isError && <p className="error">{String(price.error)}</p>}

      <h3>Create a market</h3>
      <p className="muted small">
        The template defaults to your preferred currency against USD. Fill the sponsor key,
        sponsor owner address, both feed policy hashes and the seed fields. The wallet signs
        the sponsor payload. The factory enforces the 25-field bounds, the feed policies and
        the minimum lock length.
      </p>
      <label className="field">
        Terms (JSON)
        <textarea
          rows={18}
          value={terms}
          onChange={(event) => setTerms(event.target.value)}
          className="mono"
        />
      </label>
      <button className="primary" onClick={create} disabled={busy}>
        {busy ? "Creating…" : "Create market"}
      </button>
      {created && (
        <p className="ok">
          Created {created.marketId}. Pool {created.pool}, lock {created.lock}.
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
