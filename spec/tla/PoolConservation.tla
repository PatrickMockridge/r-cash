---- MODULE PoolConservation ----
\* Pool reserves are matched one-for-one by custody; shares are minted minus
\* burned. Adds, removes and swaps preserve both equations. The model uses small
\* naturals so TLC can enumerate every transition.

EXTENDS Naturals, TLC

VARIABLES rb, rq, ts, minted, burned, pb, pq

MaxReserve == 12
MaxShares == 6
MaxMinted == 6

TypeOK ==
  /\ rb \in 0..MaxReserve
  /\ rq \in 0..MaxReserve
  /\ ts \in 0..MaxShares
  /\ minted \in 0..MaxMinted
  /\ burned \in 0..MaxMinted
  /\ pb \in 0..MaxReserve
  /\ pq \in 0..MaxReserve

Init ==
  /\ rb = 10 /\ rq = 10 /\ ts = 0
  /\ minted = 0 /\ burned = 0
  /\ pb = 10 /\ pq = 10

Add(b, q, s) ==
  /\ b \in 1..2 /\ q \in 1..2 /\ s \in 1..2
  /\ rb + b <= MaxReserve
  /\ rq + q <= MaxReserve
  /\ ts + s <= MaxShares
  /\ minted + s <= MaxMinted
  /\ rb' = rb + b
  /\ rq' = rq + q
  /\ pb' = pb + b
  /\ pq' = pq + q
  /\ ts' = ts + s
  /\ minted' = minted + s
  /\ burned' = burned

Remove(s, b, q) ==
  /\ s \in 1..2 /\ b \in 1..2 /\ q \in 1..2
  /\ s <= ts /\ b <= rb /\ q <= rq
  /\ burned + s <= MaxMinted
  /\ ts' = ts - s
  /\ burned' = burned + s
  /\ rb' = rb - b
  /\ rq' = rq - q
  /\ pb' = pb - b
  /\ pq' = pq - q
  /\ minted' = minted

SwapBase(a, o) ==
  /\ a \in 1..2 /\ o \in 1..2
  /\ a <= rb /\ o < rq
  /\ rb + a <= MaxReserve
  /\ pb + a <= MaxReserve
  /\ rb' = rb + a
  /\ rq' = rq - o
  /\ pb' = pb + a
  /\ pq' = pq - o
  /\ UNCHANGED <<ts, minted, burned>>

SwapQuote(a, o) ==
  /\ a \in 1..2 /\ o \in 1..2
  /\ a <= rq /\ o < rb
  /\ rq + a <= MaxReserve
  /\ pq + a <= MaxReserve
  /\ rq' = rq + a
  /\ rb' = rb - o
  /\ pq' = pq + a
  /\ pb' = pb - o
  /\ UNCHANGED <<ts, minted, burned>>

Next ==
  \/ \E b \in 1..2 : \E q \in 1..2 : \E s \in 1..2 : Add(b, q, s)
  \/ \E s \in 1..2 : \E b \in 1..2 : \E q \in 1..2 : Remove(s, b, q)
  \/ \E a \in 1..2 : \E o \in 1..2 : SwapBase(a, o)
  \/ \E a \in 1..2 : \E o \in 1..2 : SwapQuote(a, o)

Spec == Init /\ [][Next]_<<rb, rq, ts, minted, burned, pb, pq>>

ReservesMatchCustody == rb = pb /\ rq = pq

SharesConserved == ts = minted - burned

MintedNotBurned == minted >= burned

====
