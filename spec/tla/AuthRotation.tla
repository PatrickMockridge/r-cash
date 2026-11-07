---- MODULE AuthRotation ----
\* Rotation of an auth cell through the published Governor choke point.
\*
\* A rotation presents `domain, nonce, action, argsHash, sigs` to
\* `Governor@"authorize"`; there is no AuthAdmin contract.  `domain` is pinned
\* per auth set (`auth:<currency>:<kind>`), `action` is `"rotate"`, and the
\* threshold signatures cover `argsHash`.  The ledger creates the new auth
\* internally and takes/posts the cell.
\*
\* A facet holds the cell identity, not the auth value, so rotation leaves the
\* facet live.  A presented old auth is refused and the new auth is accepted.
\* `retired` records every value rotated out; a retired value cannot be
\* reinstated, so stale authority cannot come back.

EXTENDS Naturals, TLC

Auths == {"a1", "a2", "a3"}
Domain == "auth:<currency>:mint"
LiquidationDomain == "auth:<currency>:liquidation"
Action == "rotate"
ArgsHash == "h1"
Threshold == 2

\* The full rotation catalogue: four T1 auths, four T3 auths, two T4 auths,
\* T2's LiquidationAuthLedger and the market/directory auths.  The model is
\* parameterised by one domain; every catalogue entry uses the same protocol.
RotationDomains ==
  {"auth:<currency>:mint", "auth:<currency>:burn",
   "auth:<currency>:settle", "auth:<currency>:custody",
   "auth:<currency>:buffer-deposit", "auth:<currency>:buffer-pay",
   "auth:<currency>:buffer-cover", "auth:<currency>:savings-notify",
   "auth:<currency>:psm-mint", "auth:<currency>:psm-burn",
   "auth:<currency>:liquidation", "auth:market", "auth:directory"}

VARIABLES current, rev, retired, lastChecked, lastResult, facetLive,
          govNonce, rotations

TypeOK ==
  /\ current \in Auths
  /\ rev \in 0..4
  /\ retired \subseteq Auths
  /\ lastChecked \in Auths \union {"none"}
  /\ lastResult \in {"none", "accepted", "refused"}
  /\ facetLive \in BOOLEAN
  /\ govNonce \in 0..4
  /\ rotations \in 0..4

Init ==
  /\ current = "a1"
  /\ rev = 0
  /\ retired = {}
  /\ lastChecked = "none"
  /\ lastResult = "none"
  /\ facetLive = TRUE
  /\ govNonce = 0
  /\ rotations = 0

\* Governor-authorized rotation.  Every field is bound: the domain and action
\* identify this auth set and operation, the nonce strictly advances, the args
\* hash matches the signed schedule and the signature count reaches threshold.
RotateGov(new, nonce, domain, action, argsHash, sigs) ==
  /\ new \in Auths
  /\ nonce \in 1..4
  /\ domain = Domain
  /\ action = Action
  /\ argsHash = ArgsHash
  /\ sigs \in Threshold..2
  /\ nonce = govNonce + 1
  /\ new # current
  /\ new \notin retired
  /\ current' = new
  /\ rev' = rev + 1
  /\ retired' = retired \union {current}
  /\ lastChecked' = "none"
  /\ lastResult' = "none"
  /\ govNonce' = nonce
  /\ rotations' = rotations + 1
  /\ UNCHANGED facetLive

\* An attempt to rotate without the Governor is refused: it cannot change any
\* state.  There is no AuthAdmin contract and no caller-supplied auth.
BypassRotate(new) ==
  /\ new \in Auths
  /\ UNCHANGED <<current, rev, retired, lastChecked, lastResult, facetLive,
                 govNonce, rotations>>

\* A check records whether the presented auth is the current one.  A retired
\* value is always refused even if it could otherwise equal `current`.
Check(a) ==
  /\ a \in Auths
  /\ lastChecked' = a
  /\ lastResult' = IF a = current /\ a \notin retired THEN "accepted" ELSE "refused"
  /\ UNCHANGED <<current, rev, retired, facetLive, govNonce, rotations>>

Next ==
  \/ \E new \in Auths, nonce \in 1..4, sigs \in Threshold..2 :
       RotateGov(new, nonce, Domain, Action, ArgsHash, sigs)
  \/ \E new \in Auths : BypassRotate(new)
  \/ \E a \in Auths : Check(a)

Spec == Init /\ [][Next]_<<current, rev, retired, lastChecked, lastResult,
                                    facetLive, govNonce, rotations>>

\* An accepted check names exactly the current auth.
AcceptedIsCurrent ==
  lastResult = "accepted" => lastChecked = current

\* A refused check names a non-current (old) auth.
RefusedIsNotCurrent ==
  lastResult = "refused" => lastChecked # current

\* Rotation never leaks the old value back into service.
OldRefusedAfterRotate ==
  \A a \in retired : lastChecked = a => lastResult # "accepted"

\* The current value is never retired.
CurrentNotRetired ==
  current \notin retired

\* The facet survives rotation: it reads the cell, so it is live before and
\* after.
FacetPreserved ==
  facetLive = TRUE

\* Every rotation consumed exactly one Governor nonce; a bypass adds none.
RevEqualsNonce ==
  rev = govNonce

RotationCount ==
  rotations = rev

GovNonceBounded ==
  govNonce <= 4

\* The rotation domain is a catalogued auth set; T2's LiquidationAuthLedger is
\* one of them.
DomainInCatalogue ==
  Domain \in RotationDomains

LiquidationGoverned ==
  LiquidationDomain \in RotationDomains

====
