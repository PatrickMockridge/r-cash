---- MODULE AdminNonce ----
\* An admin action carries a strictly increasing nonce. The governor records
\* executed (nonce, action) pairs; no nonce is executed twice and each nonce
\* authorises at most one action.

EXTENDS Naturals, TLC

Actions == {"pause", "delist", "cancel"}

VARIABLES nonce, executed

TypeOK ==
  /\ nonce \in 0..3
  /\ executed \subseteq (1..3) \X Actions

Init ==
  /\ nonce = 0
  /\ executed = {}

Admin(n, a) ==
  /\ n \in 1..3
  /\ a \in Actions
  /\ n > nonce
  /\ <<n, a>> \notin executed
  /\ nonce' = n
  /\ executed' = executed \union {<<n, a>>}

Next == \E n \in 1..3 : \E a \in Actions : Admin(n, a)

Spec == Init /\ [][Next]_<<nonce, executed>>

NoReplay ==
  \A n \in 1..3, a, b \in Actions :
    (<<n, a>> \in executed /\ <<n, b>> \in executed) => a = b

ExecutedWithinNonce ==
  \A n \in 1..3, a \in Actions :
    <<n, a>> \in executed => n <= nonce

====
