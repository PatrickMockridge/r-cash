---- MODULE Provisioning ----
\* P5 reserve/confirm and P7 intra-deploy grant for per-term facet shops.
\*
\* Each facet-owning term publishes its own shop: T1 (issuer) issues
\* mint/burn/settle/custody, T3 (buffer) issues the buffer facet.  A consumer
\* maps each kind to the shop pinned for it and verifies the delivered facet
\* with that shop.
\*
\* The model also carries the multi-term consumer obligations:
\*   - T2's provisioning endpoint is the `VaultAccept` slot owner; VaultBook
\*     and LiquidationEngine are call targets, not slot owners;
\*   - the `sin > surplus` recapitalisation check is a pre-effect guard on each
\*     mint consumer (T2 VaultBook.mint, T4 PSM.buyStable), not inside the
\*     MintFacet;
\*   - a settlement with interest routes exactly that payment to the buffer
\*     through BufferOperatorFacet.
\*
\* The model checks:
\*   - a consumer slot is written at most once (no double provision);
\*   - a consumed nonce is never reserved again;
\*   - only a facet issued by the kind's pinned shop can be installed;
\*   - a rollback of a reserved nonce leaves no slot written.

EXTENDS Naturals, TLC

Consumers == {"c1", "c2"}
Kinds == {"mint", "burn", "settle", "custody", "buffer"}
Shops == {"issuer", "buffer"}
Facets == {"mint1", "buffer1"}
Nonces == 1..3

shopOf ==
  [k \in Kinds |-> IF k = "buffer" THEN "buffer" ELSE "issuer"]

facetKind == [mint1 |-> "mint", buffer1 |-> "buffer"]

facetShop == [mint1 |-> "issuer", buffer1 |-> "buffer"]

Issued == [issuer |-> {"mint1"}, buffer |-> {"buffer1"}]

\* Consumer locals.  c1 is an unrecapitalised mint consumer; c2 is healthy.
sin == [c1 |-> 1, c2 |-> 0]
surplus == [c1 |-> 0, c2 |-> 1]

\* T2's provisioning endpoint owns its slot; VaultBook/LiquidationEngine do
\* not.  The other consumer is T4's PSM endpoint.
slotOwner == [c1 |-> "VaultAccept", c2 |-> "PSM"]

VARIABLES reserved, consumed, slot, slotKind, writes,
          interestReturns, bufferDeposits

Pairs == Consumers \X Nonces

TypeOK ==
  /\ reserved \subseteq Pairs
  /\ consumed \subseteq Pairs
  /\ slot \in [Consumers -> Facets \union {"none"}]
  /\ slotKind \in [Consumers -> Kinds \union {"none"}]
  /\ writes \in [Consumers -> 0..2]
  /\ interestReturns \in 0..8
  /\ bufferDeposits \in 0..8

Init ==
  /\ reserved = {}
  /\ consumed = {}
  /\ slot = [c \in Consumers |-> "none"]
  /\ slotKind = [c \in Consumers |-> "none"]
  /\ writes = [c \in Consumers |-> 0]
  /\ interestReturns = 0
  /\ bufferDeposits = 0

\* Reserve the nonce for a consumer.  A consumer with a filled slot cannot
\* start a new provision, and a consumed nonce is refused here.
Reserve(c, n) ==
  /\ c \in Consumers
  /\ n \in Nonces
  /\ <<c, n>> \notin reserved \union consumed
  /\ slot[c] = "none"
  /\ reserved' = reserved \union {<<c, n>>}
  /\ UNCHANGED <<consumed, slot, slotKind, writes, interestReturns, bufferDeposits>>

\* Confirm: the consumer accepted a facet issued by the shop pinned for the
\* kind and wrote its private slot.  A mint consumer checks `sin <= surplus`
\* before the effect; the facet itself cannot see the buffer cell.
Confirm(c, n, k, f) ==
  /\ c \in Consumers
  /\ n \in Nonces
  /\ k \in Kinds
  /\ f \in Facets
  /\ <<c, n>> \in reserved
  /\ facetKind[f] = k
  /\ facetShop[f] = shopOf[k]
  /\ f \in Issued[shopOf[k]]
  /\ (k = "mint" => surplus[c] >= sin[c])
  /\ slot[c] = "none"
  /\ reserved' = reserved \ {<<c, n>>}
  /\ consumed' = consumed \union {<<c, n>>}
  /\ slot' = [slot EXCEPT ![c] = f]
  /\ slotKind' = [slotKind EXCEPT ![c] = k]
  /\ writes' = [writes EXCEPT ![c] = writes[c] + 1]
  /\ UNCHANGED <<interestReturns, bufferDeposits>>

\* A refused consumer call rolls the reservation back (fail() in the deploy).
Rollback(c, n) ==
  /\ <<c, n>> \in reserved
  /\ reserved' = reserved \ {<<c, n>>}
  /\ UNCHANGED <<consumed, slot, slotKind, writes, interestReturns, bufferDeposits>>

\* Replay of a consumed nonce is refused: the action cannot change state.
Replay(c, n) ==
  /\ <<c, n>> \in consumed
  /\ UNCHANGED <<reserved, consumed, slot, slotKind, writes,
                 interestReturns, bufferDeposits>>

\* A forged grant (a facet from the wrong shop, or a forged name) is refused.
ForgeGrant(c, n, k, f) ==
  /\ <<c, n>> \in reserved
  /\ ~(facetKind[f] = k /\ facetShop[f] = shopOf[k] /\ f \in Issued[shopOf[k]])
  /\ UNCHANGED <<reserved, consumed, slot, slotKind, writes,
                 interestReturns, bufferDeposits>>

\* SettlementFacet returns (true, principal, Nil) or
\* (true, principal, interestPay); T2 deposits interestPay via
\* BufferOperatorFacet.  A clean settlement deposits nothing.
Settle(c, hasInterest) ==
  /\ c \in Consumers
  /\ interestReturns < 8
  /\ \/ /\ hasInterest
        /\ interestReturns' = interestReturns + 1
        /\ bufferDeposits' = bufferDeposits + 1
     \/ /\ ~hasInterest
        /\ UNCHANGED <<interestReturns, bufferDeposits>>
  /\ UNCHANGED <<reserved, consumed, slot, slotKind, writes>>

Next ==
  \/ \E c \in Consumers, n \in Nonces : Reserve(c, n)
  \/ \E c \in Consumers, n \in Nonces, k \in Kinds, f \in Facets :
       Confirm(c, n, k, f)
  \/ \E c \in Consumers, n \in Nonces : Rollback(c, n)
  \/ \E c \in Consumers, n \in Nonces : Replay(c, n)
  \/ \E c \in Consumers, n \in Nonces, k \in Kinds, f \in Facets :
       ForgeGrant(c, n, k, f)
  \/ \E c \in Consumers, hasInterest \in BOOLEAN : Settle(c, hasInterest)

Spec == Init /\ [][Next]_<<reserved, consumed, slot, slotKind, writes,
                                    interestReturns, bufferDeposits>>

\* A consumer slot is written at most once.
NoDoubleProvision ==
  \A c \in Consumers : writes[c] <= 1

\* A consumed nonce belongs to a consumer whose slot is filled.
ConsumedDelivered ==
  \A p \in consumed : slot[p[1]] # "none"

\* Every installed facet is issued by the shop pinned for its kind.
PinnedShop ==
  \A c \in Consumers :
    slot[c] # "none" => facetShop[slot[c]] = shopOf[slotKind[c]]

\* The recorded kind matches the facet and the shop's issue set.
OnlyIssuedFacets ==
  \A c \in Consumers :
    slot[c] # "none" =>
      (facetKind[slot[c]] = slotKind[c] /\
       slot[c] \in Issued[shopOf[slotKind[c]]])

\* T2's slot is owned by VaultAccept, never by a call target.
VaultAcceptOwner ==
  slotOwner["c1"] = "VaultAccept"

CallTargetsAreNotOwners ==
  \A c \in Consumers : slotOwner[c] # "VaultBook" /\ slotOwner[c] # "LiquidationEngine"

\* Every installed mint facet belongs to a consumer that passed the
\* pre-effect recapitalisation guard.
MintConsumerRecapitalised ==
  \A c \in Consumers : slotKind[c] = "mint" => surplus[c] >= sin[c]

\* Settlement interest is routed to the buffer exactly once.
SettlementInterestRouted ==
  interestReturns = bufferDeposits

\* A clean settlement creates no buffer deposit.
NoPhantomBufferDeposit ==
  bufferDeposits <= interestReturns

\* Reservation and consumption are exclusive.
NoConsumedReservation ==
  reserved \intersect consumed = {}

====
