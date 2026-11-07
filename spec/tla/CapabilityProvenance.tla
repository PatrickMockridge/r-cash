---- MODULE CapabilityProvenance ----
\* A capability may be stored as authority only if it was created Fresh, pinned
\* by the Installer, or returned by an Issuer. A caller-supplied capability may
\* be offered, but it never enters authoritative storage.
\*
\* The multi-term additions:
\*   - a provisioned facet is attenuated by kind: a mint facet may hold only
\*     the mint scope, a burn facet only the burn scope;
\*   - a facet name is never published in a reply, attestation or data map
\*     (G-CAP-FACET).

EXTENDS Naturals, TLC

Kinds == {"mint", "burn"}
Caps == {"a1", "a2", "b1", "b2", "c1"}
Provenance == {"fresh", "installer", "issuer", "caller"}

facetOf ==
  [c \in Caps |->
     IF c \in {"a1", "a2"} THEN "mint"
     ELSE IF c \in {"b1", "b2"} THEN "burn"
     ELSE "none"]

scope == [mint |-> {"a1", "a2"}, burn |-> {"b1", "b2"}]

facetAllows(c) ==
  IF facetOf[c] = "none" THEN TRUE ELSE c \in scope[facetOf[c]]

VARIABLES provenance, stored, published

TypeOK ==
  /\ provenance \in [Caps -> Provenance]
  /\ stored \subseteq Caps
  /\ published \subseteq Caps

Init ==
  /\ provenance = [c \in Caps |->
       IF c = "c1" THEN "caller" ELSE "fresh"]
  /\ stored = {}
  /\ published = {}

\* Authoritative storage: provenance must be Fresh/Installer/Issuer, and a
\* facet-owned name must stay inside its kind's scope.
StoreAuthoritative(c) ==
  /\ c \in Caps
  /\ provenance[c] \in {"fresh", "installer", "issuer"}
  /\ facetAllows(c)
  /\ stored' = stored \union {c}
  /\ UNCHANGED <<provenance, published>>

OfferCaller(c) ==
  /\ c \in Caps
  /\ provenance[c] = "caller"
  /\ UNCHANGED <<provenance, stored, published>>

\* Expose a name in a reply, attestation or published data map.  A facet name
\* is never exposed (G-CAP-FACET).
Publish(c) ==
  /\ c \in Caps
  /\ facetOf[c] = "none"
  /\ published' = published \union {c}
  /\ UNCHANGED <<provenance, stored>>

Next ==
  \E c \in Caps : StoreAuthoritative(c) \/ OfferCaller(c) \/ Publish(c)

Spec == Init /\ [][Next]_<<provenance, stored, published>>

OnlyAuthoritative ==
  \A c \in stored : provenance[c] # "caller"

CallerNeverStored ==
  \A c \in Caps : provenance[c] = "caller" => c \notin stored

\* Facet-kind attenuation: every stored facet name is inside its scope.
FacetAttenuated ==
  \A c \in stored : facetAllows(c)

\* G-CAP-FACET: no facet name is ever published or returned.
NoFacetPublished ==
  \A c \in published : facetOf[c] = "none"

====
