---- MODULE CdpAccounting ----
\* One vault is enough to expose the accounting error in the v0.2 design:
\* supply is principal, not debt; interest accrues as a claim on collateral; a
\* write-off moves the residual to badDebt. The equations must survive borrow,
\* accrue, repay and liquidate.

EXTENDS Naturals, TLC

VARIABLES principal, interest, debt, badDebt, vaultDebt, supply

MaxDebt == 8

TypeOK ==
  /\ principal \in 0..MaxDebt /\ interest \in 0..MaxDebt
  /\ debt \in 0..MaxDebt /\ badDebt \in 0..MaxDebt
  /\ vaultDebt \in 0..MaxDebt /\ supply \in 0..MaxDebt

Init ==
  /\ principal = 0 /\ interest = 0
  /\ debt = 0 /\ badDebt = 0
  /\ vaultDebt = 0 /\ supply = 0

Borrow(a) ==
  /\ a \in 1..3
  /\ principal + a <= MaxDebt
  /\ debt + a <= MaxDebt
  /\ vaultDebt + a <= MaxDebt
  /\ supply + a <= MaxDebt
  /\ principal' = principal + a
  /\ debt' = debt + a
  /\ vaultDebt' = vaultDebt + a
  /\ supply' = supply + a
  /\ UNCHANGED <<interest, badDebt>>

Accrue(i) ==
  /\ i \in 1..2
  /\ interest + i <= MaxDebt
  /\ debt + i <= MaxDebt
  /\ vaultDebt + i <= MaxDebt
  /\ interest' = interest + i
  /\ debt' = debt + i
  /\ vaultDebt' = vaultDebt + i
  /\ UNCHANGED <<principal, badDebt, supply>>

Repay(a) ==
  /\ a \in 1..3
  /\ a <= principal
  /\ a <= debt
  /\ a <= supply
  /\ principal' = principal - a
  /\ debt' = debt - a
  /\ vaultDebt' = vaultDebt - a
  /\ supply' = supply - a
  /\ UNCHANGED <<interest, badDebt>>

Liquidate(r) ==
  /\ r \in 1..3
  /\ r <= debt
  /\ r <= vaultDebt
  /\ badDebt + r <= MaxDebt
  /\ debt' = debt - r
  /\ vaultDebt' = vaultDebt - r
  /\ badDebt' = badDebt + r
  /\ UNCHANGED <<principal, interest, supply>>

Next ==
  \/ \E a \in 1..3 : Borrow(a)
  \/ \E i \in 1..2 : Accrue(i)
  \/ \E a \in 1..3 : Repay(a)
  \/ \E r \in 1..3 : Liquidate(r)

Spec == Init /\ [][Next]_<<principal, interest, debt, badDebt, vaultDebt, supply>>

SupplyPrincipal == supply = principal

DebtEquation == debt + badDebt = principal + interest

VaultDebtMatches == debt = vaultDebt

====
