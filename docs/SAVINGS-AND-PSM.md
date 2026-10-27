# Savings, surplus and redemption (DAI-shaped)

> **Status: non-normative historical design note.** The normative behaviour is
> `docs/SPEC.md` §7–§11 and `docs/spec/20-INVARIANTS.md` (S3, S6, S9–S12). Where this note
> differs, the specification governs. Corrections since the draft:
>
> - Interest is deposited into the `SurplusBuffer`, not sent directly to `SavingsPool`.
>   The repay waterfall is `settle → cover(0) → paySavings` in one deploy; solvency before
>   yield.
> - `paySavings` is automatic on repay, moves `floor(surplus · savingsShareBps / 10000)`,
>   and skips an empty savings pool so interest is not stranded.
> - `savingsShareBps` and `psmFeeBps` are genesis fields of the signed params v2, not
>   hard-coded or seeded to zero.
> - `totalAccruedInterest` is net unsettled interest; S3 is
>   `totalDebt + sin + psmDebt = supply + totalAccruedInterest`, with `sin` outstanding and
>   `psmDebt` signed.
> - The PSM charges a configurable fee on both sides (floor gross, ceil fee), keeps fees in
>   its REV purse, and `stableDebt` may go negative: that is par redemption of vault-issued
>   stablecoin.
> - No MKR analogue, no debt auction and no recapitalisation token. Bad debt is an
>   accounting residual absorbed by the surplus buffer; residual `sin` halts new minting.

The components are created in the same `31_stablecoin` deploy as the issuer and hold only
ERTP purses and the capabilities passed at creation.

| r-cash | DAI | Role |
|---|---|---|
| `SurplusBuffer` | `vow` | holds realised interest, cancels `sin` |
| `SavingsPool` | `pot`/DSR | pays realised interest to stablecoin savers |
| `PegStabilityModule` | `dss-psm` | par redemption/issuance against a REV buffer |
| `FxPool` | secondary AMMs | secondary peg and LP spread |
| no token | MKR | bad debt beyond the buffer is an explicit shortfall |

## 1. Accounting identities

The existing identities are extended, not replaced:

- `supply = totalPrincipal` (minted stablecoins, vaults + PSM).
- `vaultDebt = Σ vault.debt`, `psmDebt` is the PSM's outstanding stablecoin.
- `totalDebt = vaultDebt` and `supply = vaultDebt + psmDebt - badDebt` is the economic
  backing identity; the PSM's REV buffer backs `psmDebt`.
- `totalAccruedInterest` becomes **unpaid accrued interest**, not a lifetime total:
  it increases when interest accrues and decreases when interest is paid to the buffer.
  `totalDebt + badDebt = supply + totalAccruedInterest` then still holds.
- Interest is paid by the borrower in stablecoins acquired on the market; the protocol
  never mints it. Principal is burned; interest is transferred to the buffer/savers.

## 2. `Stablecoin.settle`

New arm used by `VaultBook.repay`:

```
settle(payment, principal, interest, ret) -> (true, principal, interest)
```

1. Measure the payment with `issuer.getAmountOf`; require `total = principal + interest`.
2. Create a temporary purse, deposit the payment.
3. Withdraw `principal`, deposit it into the burn purse; withdraw `interest`.
4. Call `SavingsPool.notify(interestPayment)` (the buffer/savings split happens there).
5. Consume `issuerState`, recheck `totalPrincipal >= principal`, subtract `principal`, repost.
6. On any mismatch, return the payment untouched or fail the deploy (`1/0`) after a write.

`VaultBook.repay` computes:

```
interestDue = accrued - v.debt
interestPaid = min(amount, interestDue)
principalPaid = amount - interestPaid
```

- `interestPaid = 0`: use the existing `Stablecoin.burn` path.
- `principalPaid = 0`: call `SavingsPool.notify` only; supply and principal are unchanged.
- otherwise call `settle`.
- New vault debt `nd = accrued - amount`; totals add `interestDue - amount` to debt and
  `interestDue - interestPaid` to unpaid interest (which is zero when interest is paid in
  full, and `interestDue - amount` when the payment is smaller than the interest).

## 3. `SurplusBuffer` (vow)

State: `{surplus, sin, savingsShareBps, lastHeight}`. It holds a stablecoin purse.

- `deposit(payment)`: only the issuer/`settle` path (an unforgeable capability), deposit
  into the buffer purse, `surplus += amount`.
- `paySavings()`: move `savingsShareBps` of the surplus to the SavingsPool; the repay path
  calls it after `settle` so the interest reaches savers in the same deploy.
- `cover(badDebt)`: only the VaultBook capability; `sin += badDebt`; cancel
  `min(surplus, sin)` and leave the residual as explicit uncollateralised debt.
- `info`: `{surplus, sin, savingsShareBps}`.
- Governor domain `surplus-buffer` sets `savingsShareBps` within 0..10000 with a timelock.

If `sin > surplus`, `VaultBook.mint` refuses new debt until the governor recapitalises or
future interest covers it. There is no debt auction in this scope.

## 4. `SavingsPool` (pot/DSR)

State: `{totalShares, totalAssets, shares: {ownerId: amount}, rev}`. It holds a stablecoin
purse; only `notify` may add assets without minting shares. Shares are credited to the
owner derived from the caller's `deployerId`; a bare `withdraw(shares)` would let any caller
take any position.

- `deposit(dId, payment)`: derive the owner from `deployerId`, measure; `shares = amount`
  when `totalShares = 0`, else `amount * totalShares / totalAssets` (floor); deposit into
  the purse; credit `shares[ownerId] += shares`, `totalAssets += amount`; reply `(shares)`.
  There is no separate ERTP savings token in this version.
- `withdraw(dId, shares)`: only the owner's recorded shares can be withdrawn;
  `amount = totalAssets * shares / totalShares` (floor); withdraw from the purse;
  `shares[ownerId] -= shares`, `totalShares -= shares`, `totalAssets -= amount`.
- `notify(payment)`: measure, deposit, `totalAssets += amount`; no shares minted. The
  interest therefore lifts every share.
- `info`: `{totalShares, totalAssets, shareValue}`.
- No lock, no minimum, no promised rate. A share is a claim on the pool's stablecoin
  purse, not on REV collateral.

A first depositor cannot inflate the share price by donating: donations raise
`totalAssets` for existing shares, and the next depositor's shares are computed from the
new value. The pool does not accept a zero-share deposit.

## 5. `PegStabilityModule` (PSM)

State: `{revPurse, stablePurse, stableDebt, feeBps, ceiling}`. It holds a REV purse and a
stablecoin purse, and receives separate `psmMintAuth`/`psmBurnAuth` capabilities from the
issuer deploy.

- `fundRev(payment)`: governance-only; deposit REV into `revPurse`.
- `sellStable(stablePayment, revFacet, minRev)`: measure stable; burn it through
  `psmBurnAuth`; `grossRev = stableAmount * 1e8 / rate` (rate is quote per REV, e8), then
  `revOut = grossRev - grossRev*feeBps/10000`; if `revOut` exceeds the REV purse or is
  below `minRev`, refuse and return the stable payment; withdraw REV and deposit it to
  `revFacet`; `stableDebt -= stableAmount`.
- `buyStable(revPayment, stableFacet, minStable)`: measure REV; deposit into `revPurse`;
  `grossStable = revAmount * rate / 1e8`, `stableOut = grossStable -
  grossStable*feeBps/10000`; refuse at `ceiling` or below `minStable`; mint with
  `psmMintAuth`; deposit the stable payment to `stableFacet`; `stableDebt += stableOut`.
- Fees stay in `revPurse`/`stablePurse`; they are the buffer's income.
- `info`: `{stableDebt, feeBps, ceiling, revBalance}`.
- Governor domain `psm` sets the fee/ceiling and withdraws buffer only with a timelock.

The PSM is the par floor/ceiling for amounts inside its buffer; above that the AMM is the
venue. An empty buffer refuses `sellStable`; it never promises fractional redemption.
PSM-minted stablecoins count in `totalPrincipal` and in `psmDebt`, not in `vaultDebt`.

## 6. Deployment and capabilities

The `31_stablecoin` deploy creates the issuer kit, the burn purse, the REV custody purse,
the savings purse and the PSM purses. It returns the existing five URIs plus
`savingsUri` and `psmUri`; `CurrencyRegistry.register` stores all seven, and the currency
entry exposes them.

Capabilities:

- `settle`/`notify` are callable only through the VaultBook's closure capability (the
  VaultBook holds the only reference to the SavingsPool and buffer deposit).
- `psmMintAuth`/`psmBurnAuth` are created by the issuer deploy and passed only to the PSM.
- The governor domains are `surplus-buffer`, `savings-pool`, `psm`, and the existing
  `vault-book` pause.

## 7. Failure modes

| Condition | Behaviour |
|---|---|
| Payment amount ≠ principal+interest | refuse, return the payment |
| Interest payment but no principal | supply unchanged; only unpaid interest falls |
| Buffer empty, `sellStable` | refuse; no fractional redemption |
| PSM ceiling reached, `buyStable` | refuse |
| Bad debt > surplus | `sin` remains; new mint is refused until recapitalised |
| Savings pool has no assets | zero-share deposit refused |
| Oracle stale/zero | PSM and vault mint/withdraw/liquidate refuse; repay still works |

## 8. Tests

- T15: mint, advance blocks, repay interest, savings `notify`, withdraw shares; assert
  savers receive exactly the interest paid, supply falls only by principal, and S2/S3 hold.
- T16: PSM sell/buy at the oracle, fee, empty buffer, ceiling, PSM debt accounting, and
  the `stableDebt`/`supply` identity.
- Unit: a zero-interest repay, a payment smaller than the interest, a full repay, a
  donation to the savings pool, and a PSM refusal that returns the payment.
