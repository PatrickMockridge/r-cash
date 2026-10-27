import Rholphin.Model.Types

/-!
# Account factory, purse store and account

I21: only the owner's deployer id passes an account arm, and a proof is bound to
one owner.  The gate is `decide (owner = caller)`; the factory stores one
account per owner and the proof is checked by value.
-/

namespace Rholphin.Model.Identity

open Rholphin

structure Account where
  owner : Nat
  proof : Nat

structure Factory where
  accounts : List (Nat × Account)

def lookupAccount (entries : List (Nat × Account)) (key : Nat) : Option Account :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupAccount rest key

def insertAccount (entries : List (Nat × Account)) (key : Nat) (v : Account) : List (Nat × Account) :=
  (key, v) :: entries

def lookupNat (entries : List (Nat × Nat)) (key : Nat) : Option Nat :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookupNat rest key

def setNat (entries : List (Nat × Nat)) (key value : Nat) : List (Nat × Nat) :=
  (key, value) :: entries

def accountFactory_getOrCreate (f : Factory) (owner proof : Nat) : Factory × Account :=
  match lookupAccount f.accounts owner with
  | some account => (f, account)
  | none =>
      let account : Account := { owner := owner, proof := proof }
      ({ f with accounts := insertAccount f.accounts owner account }, account)

def accountFactory_verify (f : Factory) (owner proof : Nat) : Option Bool :=
  (lookupAccount f.accounts owner).map (fun account => decide (account.proof = proof))

theorem getOrCreate_verify {f : Factory} {owner proof : Nat}
    (hnone : lookupAccount f.accounts owner = none) :
    accountFactory_verify (accountFactory_getOrCreate f owner proof).1 owner proof = some true := by
  simp [accountFactory_getOrCreate, hnone, accountFactory_verify, lookupAccount, insertAccount]

def accountFactory_accountOf (f : Factory) (owner : Nat) : Option Account :=
  lookupAccount f.accounts owner

def accountGate_verify (owner caller : Nat) : Bool :=
  decide (owner = caller)

theorem gate_owner (owner : Nat) : accountGate_verify owner owner = true := by
  simp [accountGate_verify]

theorem gate_other {owner caller : Nat} (h : caller ≠ owner) :
    accountGate_verify owner caller = false := by
  simp [accountGate_verify, show ¬ owner = caller from fun hc => h hc.symm]

def purseStore_ensure (purses : List (Nat × Nat)) (asset : Nat) : List (Nat × Nat) :=
  match lookupNat purses asset with
  | some _ => purses
  | none => setNat purses asset 0

def purseStore_deposit (purses : List (Nat × Nat)) (asset amount : Nat) : List (Nat × Nat) :=
  match lookupNat (purseStore_ensure purses asset) asset with
  | some balance => setNat (purseStore_ensure purses asset) asset (balance + amount)
  | none => purseStore_ensure purses asset

def purseStore_withdraw (purses : List (Nat × Nat)) (asset amount : Nat) : List (Nat × Nat) :=
  match lookupNat (purseStore_ensure purses asset) asset with
  | some balance => setNat (purseStore_ensure purses asset) asset (balance - amount)
  | none => purseStore_ensure purses asset

def purseStore_balance (purses : List (Nat × Nat)) (asset : Nat) : Option Nat :=
  lookupNat purses asset

def purseStore_facet (purses : List (Nat × Nat)) (asset : Nat) : Option Nat :=
  lookupNat purses asset

def account_vaultOpen (f : Factory) (owner proof : Nat) : Option Bool :=
  accountFactory_verify f owner proof
def account_deposit := purseStore_deposit
def account_withdraw := purseStore_withdraw
def account_balance := purseStore_balance
def account_depositFacet := purseStore_facet
def account_sendTransfer := purseStore_withdraw
def account_claimTransfer (t : Option Nat) : Option Nat := t
def account_refundTransfer (t : Option Nat) : Option Nat := t
def account_transfers (entries : List (Nat × Nat)) : List (Nat × Nat) := entries

end Rholphin.Model.Identity
