"""Executable reference model for the R-Cash economic and mesh transitions.

This model is an independent, deliberately simple implementation used for
property and refusal tests. It is NOT the authority: docs/spec/flows and the
Lean model govern. A disagreement is a test failure, and the Lean/spec side is
corrected first if the model is the one that is wrong.

All amounts are integers in 1e8 base units; no floats.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E8 = 100_000_000
E12 = 1_000_000_000_000
BPS = 10_000


class Refused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def ceil_div(n: int, d: int) -> int:
    if d <= 0:
        return 0
    return (n + d - 1) // d


def floor_div(n: int, d: int) -> int:
    if d <= 0:
        return 0
    return n // d


def accrue(debt: int, last: int, now: int, rate: int) -> int:
    if debt <= 0 or now <= last or rate <= 0:
        return debt
    return debt + ceil_div(debt * rate * (now - last), E12)


def health(collateral: int, debt: int, rate: int, mcr_bps: int) -> bool:
    if debt <= 0:
        return True
    if rate <= 0:
        return False
    local = (collateral * rate) // E8
    return local * BPS >= debt * mcr_bps


def close_max(accrued: int, close_factor_bps: int) -> int:
    return ceil_div(accrued * close_factor_bps, BPS)


def payout(amount: int, bonus_bps: int, rate: int) -> int:
    if rate <= 0:
        return 0
    return amount * (BPS + bonus_bps) * E8 // (rate * BPS)


def savings_shares(amount: int, total_shares: int, total_assets: int) -> int:
    if total_shares == 0:
        return amount
    if total_assets == 0:
        return 0
    return amount * total_shares // total_assets


def savings_value(total_assets: int, total_shares: int, shares: int) -> int:
    if total_shares <= 0:
        return 0
    return total_assets * shares // total_shares


def fee_ceil(gross: int, fee_bps: int) -> int:
    return ceil_div(gross * fee_bps, BPS)


def buy_gross(amount: int, rate: int) -> int:
    return amount * rate // E8


def sell_gross(amount: int, rate: int) -> int:
    return 0 if rate <= 0 else amount * E8 // rate


def buy_out(amount: int, rate: int, fee_bps: int) -> int:
    gross = buy_gross(amount, rate)
    return max(0, gross - fee_ceil(gross, fee_bps))


def sell_out(amount: int, rate: int, fee_bps: int) -> int:
    gross = sell_gross(amount, rate)
    return max(0, gross - fee_ceil(gross, fee_bps))


def amm_value(rb: int, rq: int, rate: int) -> int:
    return rb * rate // E8 + rq


def amm_weight(rb: int, rq: int, rate: int) -> int:
    value = amm_value(rb, rq, rate)
    if value <= 0:
        return BPS // 2
    return (rb * rate // E8) * BPS // value


def amm_fee(weight: int, base_spread: int, skew_spread: int) -> int:
    half = BPS // 2
    extra = (abs(weight - half) * skew_spread) // half if half else 0
    return base_spread + extra


def amm_out_b2q(dx: int, rate: int, fee_bps: int) -> int:
    return (dx * rate // E8) * (BPS - fee_bps) // BPS


def amm_out_q2b(dx: int, rate: int, fee_bps: int) -> int:
    if rate <= 0:
        return 0
    return (dx * E8 // rate) * (BPS - fee_bps) // BPS


def lp_shares(deposit_value: int, total_shares: int, pool_value: int, first: bool) -> int:
    if first:
        return max(0, deposit_value - E8)
    if total_shares <= 0 or pool_value <= 0:
        return 0
    return deposit_value * total_shares // pool_value


@dataclass
class Ledger:
    total_principal: int = 0
    supply: int = 0
    total_debt: int = 0
    total_accrued_interest: int = 0
    sin: int = 0
    psm_debt: int = 0
    bad_debt: int = 0


def s1(l: Ledger) -> bool:
    return l.supply == l.total_principal


def s3(l: Ledger) -> bool:
    return l.total_debt + l.sin + l.psm_debt == l.supply + l.total_accrued_interest


def mint(l: Ledger, amount: int, accrued: int, stored: int) -> Ledger:
    return Ledger(
        total_principal=l.total_principal + amount,
        supply=l.supply + amount,
        total_debt=l.total_debt + (accrued - stored) + amount,
        total_accrued_interest=l.total_accrued_interest + (accrued - stored),
        sin=l.sin,
        psm_debt=l.psm_debt,
        bad_debt=l.bad_debt,
    )


def burn(l: Ledger, amount: int) -> Ledger:
    return Ledger(l.total_principal - amount, l.supply - amount, l.total_debt,
                  l.total_accrued_interest, l.sin, l.psm_debt, l.bad_debt)


def repay(l: Ledger, amount: int, interest_paid: int, principal_paid: int,
          cancelled: int, accrued: int, stored: int) -> Ledger:
    assert principal_paid + interest_paid == amount
    return Ledger(
        total_principal=l.total_principal - principal_paid - cancelled,
        supply=l.supply - principal_paid - cancelled,
        total_debt=l.total_debt + (accrued - stored) - amount,
        total_accrued_interest=l.total_accrued_interest + (accrued - stored) - interest_paid,
        sin=l.sin - cancelled,
        psm_debt=l.psm_debt,
        bad_debt=l.bad_debt,
    )


def liquidate(l: Ledger, amount: int, accrued: int, stored: int) -> Ledger:
    return Ledger(
        total_principal=l.total_principal - amount,
        supply=l.supply - amount,
        total_debt=l.total_debt + (accrued - stored) - amount,
        total_accrued_interest=l.total_accrued_interest + (accrued - stored),
        sin=l.sin,
        psm_debt=l.psm_debt,
        bad_debt=l.bad_debt,
    )


def write_off(l: Ledger, amount: int, accrued: int, stored: int, cancelled: int) -> Ledger:
    return Ledger(
        total_principal=l.total_principal - amount - cancelled,
        supply=l.supply - amount - cancelled,
        total_debt=l.total_debt - stored,
        total_accrued_interest=l.total_accrued_interest + (accrued - stored),
        sin=l.sin + (accrued - amount) - cancelled,
        psm_debt=l.psm_debt,
        bad_debt=l.bad_debt + (accrued - amount),
    )


def psm_buy(l: Ledger, out: int) -> Ledger:
    return Ledger(l.total_principal + out, l.supply + out, l.total_debt,
                  l.total_accrued_interest, l.sin, l.psm_debt + out, l.bad_debt)


def psm_sell(l: Ledger, amount: int) -> Ledger:
    return Ledger(l.total_principal - amount, l.supply - amount, l.total_debt,
                  l.total_accrued_interest, l.sin, l.psm_debt - amount, l.bad_debt)


def cover0(l: Ledger, cancelled: int) -> Ledger:
    return Ledger(l.total_principal - cancelled, l.supply - cancelled, l.total_debt,
                  l.total_accrued_interest, l.sin - cancelled, l.psm_debt, l.bad_debt)


def accrual_delta(l: Ledger, delta: int) -> Ledger:
    return Ledger(l.total_principal, l.supply, l.total_debt + delta,
                  l.total_accrued_interest + delta, l.sin, l.psm_debt, l.bad_debt)


@dataclass
class Vault:
    collateral: int = 0
    debt: int = 0
    last_height: int = 0


@dataclass
class Book:
    vaults: dict[str, Vault] = field(default_factory=dict)
    total_debt: int = 0
    total_collateral: int = 0
    total_accrued_interest: int = 0
    bad_debt: int = 0

    def sum_debt(self) -> int:
        return sum(v.debt for v in self.vaults.values())

    def sum_collateral(self) -> int:
        return sum(v.collateral for v in self.vaults.values())


def s2(b: Book) -> bool:
    return b.total_debt == b.sum_debt() and b.total_collateral == b.sum_collateral()


def deposit(b: Book, owner: str, amount: int, accrued: int) -> Book:
    v = b.vaults.get(owner, Vault())
    new = Vault(v.collateral + amount, accrued, v.last_height)
    return Book({**b.vaults, owner: new}, b.total_debt + accrued - v.debt,
                b.total_collateral + amount, b.total_accrued_interest + accrued - v.debt,
                b.bad_debt)


def withdraw(b: Book, owner: str, amount: int, accrued: int) -> Book:
    v = b.vaults[owner]
    if amount > v.collateral:
        raise Refused("amount")
    new = Vault(v.collateral - amount, accrued, v.last_height)
    return Book({**b.vaults, owner: new}, b.total_debt + accrued - v.debt,
                b.total_collateral - amount, b.total_accrued_interest + accrued - v.debt,
                b.bad_debt)


def book_mint(b: Book, owner: str, amount: int, accrued: int) -> Book:
    v = b.vaults[owner]
    new = Vault(v.collateral, accrued + amount, v.last_height)
    return Book({**b.vaults, owner: new}, b.total_debt + accrued - v.debt + amount,
                b.total_collateral, b.total_accrued_interest + accrued - v.debt,
                b.bad_debt)


@dataclass
class Savings:
    total_shares: int = 0
    total_assets: int = 0
    shares: dict[str, int] = field(default_factory=dict)

    def sum_shares(self) -> int:
        return sum(self.shares.values())


def s10(s: Savings) -> bool:
    return s.total_shares == s.sum_shares()


def savings_deposit(s: Savings, owner: str, amount: int, shares: int) -> Savings:
    return Savings(s.total_shares + shares, s.total_assets + amount,
                   {**s.shares, owner: s.shares.get(owner, 0) + shares})


def savings_withdraw(s: Savings, owner: str, shares: int, amount: int) -> Savings:
    held = s.shares.get(owner, 0)
    if shares <= 0 or shares > held:
        raise Refused("shares")
    return Savings(s.total_shares - shares, s.total_assets - amount,
                   {**s.shares, owner: held - shares})


@dataclass
class Buffer:
    surplus: int = 0
    sin: int = 0
    savings_share_bps: int = 0


def cover(b: Buffer, bad_debt: int) -> tuple[Buffer, int]:
    if bad_debt < 0:
        raise Refused("amount")
    new_sin = b.sin + bad_debt
    cancelled = min(b.surplus, new_sin)
    return Buffer(b.surplus - cancelled, new_sin - cancelled, b.savings_share_bps), cancelled


def pay_savings(b: Buffer) -> tuple[Buffer, int]:
    move = b.surplus * b.savings_share_bps // BPS
    if move <= 0:
        return b, 0
    return Buffer(b.surplus - move, b.sin, b.savings_share_bps), move


@dataclass
class Psm:
    stable_debt: int = 0
    ceiling: int = 0
    fee_bps: int = 0
    max_supply: int = 0


def psm_buy_state(p: Psm, out: int) -> Psm:
    if p.stable_debt + out > p.ceiling:
        raise Refused("ceiling")
    return Psm(p.stable_debt + out, p.ceiling, p.fee_bps, p.max_supply)


def psm_sell_state(p: Psm, amount: int) -> Psm:
    if p.stable_debt - amount < -p.max_supply:
        raise Refused("psm floor")
    return Psm(p.stable_debt - amount, p.ceiling, p.fee_bps, p.max_supply)


@dataclass(frozen=True)
class Market:
    market_id: str
    base: str
    quote: str
    status: str = "draft"
    version: int = 1


@dataclass
class Index:
    markets: dict[str, Market] = field(default_factory=dict)
    by_pair: dict[str, str] = field(default_factory=dict)


def pair_keys(base: str, quote: str) -> tuple[str, str]:
    return f"market:{base}/{quote}", f"market:{quote}/{base}"


def stage(index: Index, market: Market) -> Index:
    direct, reverse = pair_keys(market.base, market.quote)
    prior_id = index.by_pair.get(direct) or index.by_pair.get(reverse)
    if prior_id is not None:
        prior = index.markets[prior_id]
        if prior.status in ("active", "paused"):
            raise Refused("pair active")
        if market.version <= prior.version:
            raise Refused("version")
    markets = {**index.markets, market.market_id: market}
    by_pair = {**index.by_pair, direct: market.market_id, reverse: market.market_id}
    return Index(markets, by_pair)


def market_for(index: Index, base: str, quote: str) -> Market | None:
    direct, reverse = pair_keys(base, quote)
    market_id = index.by_pair.get(direct) or index.by_pair.get(reverse)
    return index.markets.get(market_id) if market_id else None


def pause_asset(index: Index, code: str) -> Index:
    markets = {
        mid: (Market(m.market_id, m.base, m.quote, "paused", m.version)
              if m.status == "active" and (m.base == code or m.quote == code) else m)
        for mid, m in index.markets.items()
    }
    return Index(markets, dict(index.by_pair))


@dataclass(frozen=True)
class ExternalEntry:
    code: str
    kind: str
    asset_uri: str
    decimals: int
    sponsor: str


def external_entry(code: str, kind: str, asset_uri: str, decimals: int, sponsor: str) -> ExternalEntry:
    if kind != "external":
        raise Refused("external kind")
    if decimals != 8:
        raise Refused("external decimals")
    if not asset_uri:
        raise Refused("external attestation")
    return ExternalEntry(code, kind, asset_uri, decimals, sponsor)


def load_mesh() -> dict:
    return json.loads((ROOT / "configs" / "mesh.json").read_text())
