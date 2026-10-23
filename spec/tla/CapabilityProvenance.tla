---- MODULE CapabilityProvenance ----
\* A capability may be stored as authority only if it was created Fresh, pinned
\* by the Installer, or returned by an Issuer. A caller-supplied capability may
\* be offered, but it never enters authoritative storage.

EXTENDS Naturals, TLC

Caps == {"c1", "c2", "c3"}
Provenance == {"fresh", "installer", "issuer", "caller"}

VARIABLES provenance, stored

TypeOK ==
  /\ provenance \in [Caps -> Provenance]
  /\ stored \subseteq Caps

Init ==
  /\ provenance = [c \in Caps |->
       IF c = "c1" THEN "caller" ELSE "fresh"]
  /\ stored = {}

StoreAuthoritative(c) ==
  /\ c \in Caps
  /\ provenance[c] \in {"fresh", "installer", "issuer"}
  /\ stored' = stored \union {c}
  /\ UNCHANGED provenance

OfferCaller(c) ==
  /\ c \in Caps
  /\ provenance[c] = "caller"
  /\ UNCHANGED <<provenance, stored>>

Next == \E c \in Caps : StoreAuthoritative(c) \/ OfferCaller(c)

Spec == Init /\ [][Next]_<<provenance, stored>>

OnlyAuthoritative ==
  \A c \in stored : provenance[c] # "caller"

CallerNeverStored ==
  \A c \in Caps : provenance[c] = "caller" => c \notin stored

====
