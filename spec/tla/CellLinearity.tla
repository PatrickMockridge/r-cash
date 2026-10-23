---- MODULE CellLinearity ----
\* A state cell is Empty or Full; exactly one actor may hold a consumed cell at a
\* time, and a holder must post before another take. This is the finite model of
\* the RECV/PEEK/POST protocol in docs/spec/00-CALCULUS.md.

EXTENDS Naturals, TLC

Actors == {"a1", "a2"}

VARIABLES cell, held

TypeOK ==
  /\ cell \in {"Empty", "Full"}
  /\ held \in [Actors -> BOOLEAN]

Init ==
  /\ cell = "Full"
  /\ held = [a \in Actors |-> FALSE]

Take(a) ==
  /\ a \in Actors
  /\ cell = "Full"
  /\ ~held[a]
  /\ cell' = "Empty"
  /\ held' = [held EXCEPT ![a] = TRUE]

Put(a) ==
  /\ a \in Actors
  /\ held[a]
  /\ cell = "Empty"
  /\ cell' = "Full"
  /\ held' = [held EXCEPT ![a] = FALSE]

Next == \E a \in Actors : Take(a) \/ Put(a)

Spec == Init /\ [][Next]_<<cell, held>>

NoDoubleTake == \A a, b \in Actors : (held[a] /\ held[b]) => a = b

QuiescentFull == (\A a \in Actors : ~held[a]) => cell = "Full"

HeldMeansEmpty == \A a \in Actors : held[a] => cell = "Empty"

====
