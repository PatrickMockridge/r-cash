---- MODULE TransferExclusivity ----
\* Each transfer is its own cell. A transfer is open or terminal; a terminal
\* transfer has released its payment. Claim and refund race on the same cell and
\* exactly one wins. terminalCount records the number of terminal transitions so
\* the model checks that a transfer never terminates twice.

EXTENDS Naturals, TLC

Transfers == {"t1", "t2"}

VARIABLES status, payment, terminalCount

TypeOK ==
  /\ status \in [Transfers -> {"open", "claimed", "refunded"}]
  /\ payment \in [Transfers -> {"held", "gone"}]
  /\ terminalCount \in [Transfers -> 0..2]

Init ==
  /\ status = [t \in Transfers |-> "open"]
  /\ payment = [t \in Transfers |-> "held"]
  /\ terminalCount = [t \in Transfers |-> 0]

Claim(t) ==
  /\ t \in Transfers
  /\ status[t] = "open"
  /\ status' = [status EXCEPT ![t] = "claimed"]
  /\ payment' = [payment EXCEPT ![t] = "gone"]
  /\ terminalCount' = [terminalCount EXCEPT ![t] = terminalCount[t] + 1]

Refund(t) ==
  /\ t \in Transfers
  /\ status[t] = "open"
  /\ status' = [status EXCEPT ![t] = "refunded"]
  /\ payment' = [payment EXCEPT ![t] = "gone"]
  /\ terminalCount' = [terminalCount EXCEPT ![t] = terminalCount[t] + 1]

Next == \E t \in Transfers : Claim(t) \/ Refund(t)

Spec == Init /\ [][Next]_<<status, payment, terminalCount>>

Exclusive ==
  \A t \in Transfers :
    status[t] \in {"claimed", "refunded"} => payment[t] = "gone"

OpenHeld ==
  \A t \in Transfers :
    status[t] = "open" => payment[t] = "held"

AtMostOneTerminal ==
  \A t \in Transfers : terminalCount[t] <= 1

====
