# 00 — Component calculus

## 1. Types

```
τ ::= 1 | Bool | Int | Bytes | String
    | τ × τ | List τ | Map κ τ
    | Name⟨τ⟩ | Cap⟨π⟩ | Payment⟨β⟩ | Purse⟨β⟩ | Cell⟨τ⟩

π ::= { op_i : In_i → Out_i }_i
σ ::= 1 | τ

AssetId  = String            -- "REV" | "NGN" | "LP:NGN/KES:v3"
OwnerId  = String            -- rev address derived from the owner public key
Hex      = String
Hash     = Bytes
Uri      = String            -- registry URI, a value
Cap      = Name              -- unforgeable channel implementing an interface
ret      = Name              -- fresh reply channel; every arm replies exactly once
```

`Map` is a persistent value, not a channel. State is a value (`@s`) inside a `Cell`.
`Payment⟨β⟩` is linear ERTP value; `Purse⟨β⟩` is an ERTP custody object.

## 2. Components

A component is

```
C = (id, S, c, π, δ, Inv)
```

- `id` is a stable identity (`component:currency-registry`, `zone:NGN`,
  `market:KES/NGN:v3:pool`, `transfer:<book-id>:<n>`);
- `S` is the state type in the component's cell;
- `c : Name⟨Cell⟨S⟩⟩` is exactly one state cell, created by `new` inside the component
  family and never exposed outside it;
- `π = { op_i : In_i → Out_i }` is the interface;
- `δ ⊆ S × Op ⇀ S × Reply` is the partial transition relation, with
  `Op = Σ_i op_i(In_i, ret : Name⟨Out_i⟩)` and
  `Reply = (true, Out_i) + (false, Reason)`;
- `Inv ⊆ S × H` is the invariant over state and observable history `H = List(Event)`,
  `Event = (op, reply)`.

An operation outside `dom δ` is a **refusal**. It replies `(false, reason)` and leaves the
cell as `Full(s)`.

## 3. State cells

```
Cell⟨σ⟩ = Empty ⊕ Full(σ)
Full_c(s) ≡ c!s
Empty     ≡ no message on c
```

Operational rules:

```
(RECV)  c!s | for (@s <- c) { P }   →   Hold_c(s) ⊗ P[s]
(PEEK)  c!s | for (@s <<- c) { P }  →   c!s ⊗ P[s]
(POST)  Hold_c(s')                  →   c!s'
(DUP)   Hold_c(s)                   →   Hold_c(s) ⊗ Hold_c(s)     FORBIDDEN
(DROP)  Hold_c(s)                   →   0                         FORBIDDEN
```

`Hold_c(s)` is a linear hypothesis, created by `RECV` and eliminated by `POST`. Rholang
correspondence is exact: `for (@s <- cell)` consumes, `for (@s <<- cell)` peeks, and
`cell!s'` restores.

**Hold is not a lock.** It blocks another `RECV`, not a `PEEK`, and it does not isolate a
native purse. It does not survive a deploy boundary.

## 4. Capability provenance

```
prov(cap) ::= Fresh(C)     created by C with `new`
            | Installer    created by the bootstrap and pinned in Root
            | Issuer(A)    returned by an authority A in a documented arm
            | Caller       supplied by an arbitrary caller
```

**C1.** A component may store or use a capability as authority only if
`prov(cap) ∈ {Fresh, Installer, Issuer}`. A `Caller` capability may be an input payment or
a reply channel, never an authoritative dependency.

**C2 (no caller callbacks).** No component may send to a caller-supplied name while
holding a consumed cell or after an irreversible write. Callback-shaped parameters
(`depositFacet`, a caller-provided book or pool) are replaced by returned values.

**C3 (bundle capture).** A bundled contract may close over:

- system channels (`rho:block:data`, `rho:crypto:*`, `rho:registry:lookup`,
  `rho:rchain:deployerId:ops`, `rho:rchain:ertp`, `rho:rev:address`,
  `rho:rchain:deployId`);
- immutable values (strings, bytes, maps, URI strings, stable keys);
- names created by `new` in the same term (own cells, child contracts, proofs, tokens).

It may **not** close over any name obtained from `Root.resolve`, `ZoneDirectory`,
`OracleRegistry`, `MarketDirectory`, `CurrencyRegistry` or `rho:registry:lookup`. The
`03_accounts` continuation failure is this case: `AccountFactory` was bundled while closing
over a live `ListingRegistry` capability read from `ComponentRegistry`. v3 carries
`rootUri` strings and resolves per arm.

## 5. Interface well-formedness

```
WF1  single writer:    owns(C) = c; only C's internal contracts consume c
WF2  one reply:        every invocation produces exactly one ret message
WF3  refusal purity:   a refusal leaves c as Full(s)
WF4  invariance:       s ⊨ Inv ∧ δ(s,op) = (s',o) ⇒ s' ⊨ Inv
WF5  linearity:        every mutating arm consumes c once and posts c once
WF6  responsiveness:   while Hold_c(s), every await is to a Responsive name
WF7  authority:        every stored Cap has provenance ≠ Caller
WF8  bundleability:    free(C) ⊆ SystemChannels ∪ cells(C) ∪ values/URIs
```

`Responsive` means a native channel, or a component satisfying WF1–WF6 whose arms do not
await a caller-supplied name. Every arm must match ERTP replies exhaustively
(`(true, x)` and `(false, e)`); never `@_`.

## 6. Laws

These hold and must be preserved.

- **L1 Quiescent linearity.** In every reachable quiescent state of a well-formed
  component, the cell contains exactly one `Full` message. No duplication, no loss. A
  consumed cell whose continuation awaits a name that never replies violates liveness and
  is the "committed consumed cell" failure.
- **L2 Single writer.** Exactly one component owns each cell. Views are projections; a
  second authoritative copy is a defect.
- **L3 Capability provenance.** Authority is `Fresh`, `Installer` or `Issuer`; caller
  capabilities are payments and reply channels only.
- **L4 Conservation.** For each brand, `minted − burned = Σ purses + Σ payments`. Pool
  reserves equal custody; each open transfer cell holds exactly its payment; lock shares
  equal its LP purse; zone custody covers collateral.
- **L5 Single-cell serialisability.** A one-cell read-modify-write is equivalent to an
  atomic operation. The `RECV` is the linearization point.
- **L6 Joint invariants are co-located.** If an invariant cannot be preserved by one cell,
  the state lives in one named atomic cluster, or the operation uses the documented
  reserve/confirm protocol. Splitting an invariant across cells is a design error.
- **L7 Data-only state, with named exceptions.** State stores strings, integers, bytes,
  lists and maps. Live names are allowed only for own `new`-bound cells, ERTP
  purses/payments, per-account vault auths, per-transfer cells and claim tokens.
  Registry-resolved capabilities and caller-supplied caps are never stored.
- **L8 Bounded units.** Every unit has a byte, depth and contract-count budget. A unit over
  budget is split; it is never inlined further.

These do **not** hold across an await:

- **N1** no multi-cell atomicity;
- **N2** no read-modify-write across an await;
- **N3** a `PEEK` observes intermediate states;
- **N4** no FIFO delivery guarantee;
- **N5** no liveness for an unmatched receive;
- **N6** no runtime provenance check on a name;
- **N7** no rollback on a business refusal; only `fail()` aborts the deploy.

## 7. Composition protocols

Only these shapes are legal.

### P1 — Single-cell commit

```
consume c; validate; compute; post c'; reply
```

Registrations, status transitions, nonce updates. No external await while `c` is held.

### P2 — Await-then-commit

```
await all external reads;
consume c; validate against the fresh snapshot and the read values; post c'; reply
```

Quotes, activation evidence, feed reads. The decision is a snapshot event, not an ongoing
invariant.

### P3 — Effect-then-commit

```
validate on peek;
perform exactly one external effect to a pinned callee;
consume c; revalidate;
post c'; reply;
if revalidation fails after the effect: fail()
```

`TransferBook.send`, `FxPool.swap`, any arm that moves value before a local write. `fail()`
reverts the whole deploy, including the external effect.

### P4 — Hold-through-native

```
consume c; compute; post c';
call a native ERTP/clock channel;
if it refuses: fail()
```

The only protocol that may hold a cell across an await, because native channels are
responsive. Used by mint/burn, collateral custody, lock funding and claim payout. If any
write preceded the native call, a refusal calls `fail()`; it never returns `(false, …)`.

### P5 — Reserve/confirm

```
reserve id; perform external work; confirm
```

Only for operations that must cross a deploy boundary. Not used in v3; kept as a documented
fallback for a future multi-deploy saga.

### P6 — Fail-closed

All business validation precedes the first write. After a withdrawal, mint, burn, swap or
escrow move, an unexpected refusal calls `fail()`. No arm returns `(false, reason)` after
moving value.

## 8. Safety rules

| ID | Rule |
|---|---|
| S1 | Never peek a cell, await an external component, then write the peeked snapshot. Consume after the await or not at all. |
| S2 | Never await a caller-supplied name while holding a consumed cell. |
| S3 | Never store a caller-supplied capability as authority. |
| S4 | Never close a bundled contract over a capability resolved from a registry. Carry URIs and resolve at arm entry. |
| S5 | Revalidate the consumed state after any external read or effect. |
| S6 | Every refusal after a write or value movement calls `fail()`. |
| S7 | Match ERTP replies exhaustively; never a catch-all `@_`. |
| S8 | All business validation precedes the first write. |
| S9 | Every arm replies exactly once, including every refusal. |
| S10 | One copy of each truth; derived views are projections. |
| S11 | A state record nests at most 8 map levels; a deploy defines at most 8 contracts. |
| S12 | Every canonical term field is enforced on-chain or removed. |
| S13 | The admin nonce and the effect it authorizes are in the same cell, or the nonce is owned by `Governor` and the effect is idempotent. |
| S14 | Internal sub-contract calls carry a fresh one-shot token minted by the facade. |
| S15 | Transfer exclusivity is a per-transfer cell consume; there is no shared escrow purse. |
| S16 | Activation evidence is immutable attestation, never live mutable reserves. |
| S17 | Every callee that can move value is pinned by `MarketDirectory`, `CurrencyRegistry` or `Root` and checked against the terms hash. |
| S18 | Every deploy term passes the size, depth and capture gates before it is signed. |

## 9. Resource budgets

| Budget | Platform limit | Target | Hard fail |
|---|---|---|---|
| Minified deploy term | 65,536 bytes | ≤ 24 KiB | 56 KiB |
| Source file | — | ≤ 450 lines, ≤ 8 contracts | 600 lines, 12 contracts |
| Parser nesting | 128 | ≤ 48 | 96 |
| AST depth | 768 | ≤ 96 | 192 |
| Operator chain | 512 | ≤ 128 | 256 |
| Runtime value depth | 256 | ≤ 8 map levels | 16 |
| Deploy lifespan | 50 blocks | anchor at the tip; one unit per deploy | — |
| Install phlo | 100M | ≤ 60M | 80M |

The conservative depth checker in `tools/measure_contracts.py` is the offline gate; the
devnet parse/normalize step is authoritative. An arm may nest at most four
`for`/`match`/`if` levels before delegating to a helper contract.

## 10. Worked ordering

`FxPool.swap(src, payment, minOut)`:

1. resolve `Root`, `MarketIndex`, `OracleHub`, `AmmMath` and `Clock` URIs;
2. peek `poolState`; refuse if paused or below depth/ticket;
3. read the payment amount through the issuer;
4. read the pair rate and market status; refuse if the market is not active or the feed is
   stale;
5. call `AmmMath.out` with the peeked reserves; receive `out`, `fee`;
6. consume the payment and `poolState`; revalidate reserves, status, terms hash and pause;
7. write reserves and share totals; withdraw `out` to the caller; `fail()` on any native
   refusal;
8. reply `(true, out, payment, fee)`.

No cell is held while `AmmMath`, `OracleHub` or the issuer is awaited. If the consumed
reserves differ from the peeked reserves, step 6 calls `fail()` and the client retries.
