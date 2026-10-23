# Threat model (MVP)

## Assets

- Native REV collateral held by the stablecoin issuer (`VaultBook`/`CollateralCustody`).
- Local stablecoins (rNGN, rKES) held in Accounts, pools and transfer escrow.
- LP tokens and pool reserves.
- Claim secrets (bearer authority over escrowed transfer funds).
- Account proofs; issuer vault authorities are separate per-vault capabilities.
- Oracle prices (issuer collateral and FX).

## Adversaries

- A user with a key but no privileges.
- A malicious caller of a public contract arm.
- A malicious/compromised oracle reporter or ramp partner.
- A contract-level bug (state cell consumed, partial commit).
- A proposer influencing block timestamp (not used for economics).
- A chain-level adversary (pre-testnet consensus residuals; out of scope for the app but a reason
  this is devnet-only).

## Key threats and mitigations

| Threat | Mitigation |
|---|---|
| DeployerId capability stolen by a contract | Only `Account` receives it; one read-only `pubKeyBytes` call; never stored/emitted; lint + probe |
| Silent unmatched receive commits a consumed state cell | Every arm replies; native-only or trusted responders while holding state; `fail()` on unexpected refusal; deadlock probe |
| Partial value movement on failure | Validate-before-write; deploy-level rollback of tuple space and native state; late-failure tests |
| Wrong-brand/amount payment accepted | Every contract measures payments via the issuer; refuses mismatch before depositing |
| Double claim / double deposit | ERTP payment consumed on first deposit; transfer status checked; claim secret hash; adversarial tests |
| Refund before expiry / claim after expiry | Block-height checks in `TransferBook` |
| Claim secret loss | Sender refunds after expiry; no recovery service; documented |
| Oracle manipulation / stale feed | 2-of-3 reporters, median, spread and freshness checks, absolute band, pause; issuer mint and swap actions require fresh |
| Oracle reporter key compromise | Quorum threshold; governance can replace reporters; documented trust |
| Issuer liquidation cascade / bad debt | 200% MCR, partial close factor, liquidation bonus; no stability pool in MVP |
| First-depositor LP inflation | `MINIMUM_LIQUIDITY` burned; oracle-checked first deposit; floor/ceil rules |
| Rounding drains value | Outputs floor, debts/fees up; property tests |
| Ramp takes the secret and does not pay fiat | Allowlisted ramps; no bond in MVP; documented trust; bonded ramps later |
| Ramp takes fiat and does not on-ramp | Same; off-chain disputes; later bond/slashing |
| Forged admin/oracle action | DER signature verification over a canonical prehash; URI-bound actions; nonce replay guard |
| Channel substitution in an admin action | Actions are signed; the Directory/Components are locked after installation |
| Registry redirection during installation | Components is unlocked only until the TransferBook deploy locks it; installation is a trusted deployer sequence (A4). Production SHOULD use signed URI-bound registration |
| Map state growth / O(N) writes | Measured; sharding/pruning later; bounded demo |
| Parser/normalizer traps | Parse-check every contract; all contract names `new`-bound; reply-shape tests |
| Block timestamp manipulation | Contracts use block height, not timestamp, for staleness/interest |
| Chain-level consensus fault | Devnet-only; no real funds; public testnet + audit required |

## Residual risks

- The oracle committee and ramp allowlist are trusted in the MVP.
- REV price volatility can produce bad debt; there is no backstop.
- Claim mode hides the recipient on-chain, but the ramp learns payout details; amounts are public.
- The protocol has no KYC/AML; regulated partners are the compliance boundary.
- rchain-rust is pre-testnet; consensus residuals are an external risk.
