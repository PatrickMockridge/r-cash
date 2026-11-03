---- MODULE PoolCriticalSection ----
\* The FxPool P3 commit protocol.
\*
\* The pre-fix arm took `poolState` at entry and then awaited OracleHub,
\* MarketIndex, AmmMath, the issuer and the purses. The fix peeks, performs all
\* external reads and math while the cell is free, then takes, revalidates `rev`,
\* performs the native effect, and posts. The invariant states that the cell is
\* never held during an external read phase.
EXTENDS Naturals

VARIABLES phase, held, revSeen, revLive

Init ==
    /\ phase = "idle"
    /\ held = FALSE
    /\ revSeen = 0
    /\ revLive = 0

Peek ==
    /\ phase = "idle"
    /\ phase' = "peek"
    /\ revSeen' = revLive
    /\ UNCHANGED <<held, revLive>>

\* External reads (oracle, index, issuer) happen while the cell is free.
Read ==
    /\ phase = "peek"
    /\ phase' = "read"
    /\ UNCHANGED <<held, revSeen, revLive>>

\* The only take is after all reads.
Take ==
    /\ phase = "read"
    /\ held' = TRUE
    /\ phase' = "take"
    /\ UNCHANGED <<revSeen, revLive>>

\* Revalidation: a changed rev is a conflict, not an effect.
Revalidate ==
    /\ phase = "take"
    /\ revLive = revSeen
    /\ phase' = "effect"
    /\ UNCHANGED <<held, revSeen, revLive>>

Conflict ==
    /\ phase = "take"
    /\ revLive # revSeen
    /\ held' = FALSE
    /\ phase' = "idle"
    /\ UNCHANGED <<revSeen, revLive>>

\* The native deposit/withdraw and the post.
Effect ==
    /\ phase = "effect"
    /\ phase' = "post"
    /\ revLive' = revLive + 1
    /\ UNCHANGED <<held, revSeen>>

Post ==
    /\ phase = "post"
    /\ held' = FALSE
    /\ phase' = "idle"
    /\ UNCHANGED <<revSeen, revLive>>

Next == Peek \/ Read \/ Take \/ Revalidate \/ Conflict \/ Effect \/ Post

Spec == Init /\ [][Next]_<<phase, held, revSeen, revLive>>

\* The pre-fix ordering (take at idle, then read) violates this: it reaches
\* `held` in phase "read". The fixed actions never do.
NoHoldDuringRead == held => phase # "read"

====
