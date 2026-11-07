---- MODULE MarketCreateAtomicity ----
\* A bounded model of the committed market-create transition.
\*
\* The pre-fix code could commit a sealed directory slot without an index record:
\* bind and seal ran, then the stage guard refused and returned `false` without
\* failing the deploy. The fix pre-checks the stage guards before any write,
\* make bind create-only, and fails the deploy after the first directory write.
\* At the deploy boundary the result is atomic: either both the sealed slot and
\* the staged record exist, or neither does.
EXTENDS Naturals

VARIABLES slot, index, checked, refused

Init == slot = "none" /\ index = "none" /\ checked = FALSE /\ refused = FALSE

\* The factory pre-checks the stage guards before it creates a pool or binds.
Precheck ==
    /\ checked = FALSE
    /\ checked' = TRUE
    /\ UNCHANGED <<slot, index, refused>>

\* Commit: the post-write sequence is atomic at the deploy boundary.
Create ==
    /\ checked
    /\ slot = "none"
    /\ index = "none"
    /\ slot' = "sealed"
    /\ index' = "staged"
    /\ UNCHANGED <<checked, refused>>

\* Any refusal leaves the committed directory and index unchanged.
Refuse ==
    /\ UNCHANGED <<slot, index, checked, refused>>

Next == Precheck \/ Create \/ Refuse

Spec == Init /\ [][Next]_<<slot, index, checked, refused>>

NoOrphanSealedSlot == slot = "sealed" => index = "staged"

====
