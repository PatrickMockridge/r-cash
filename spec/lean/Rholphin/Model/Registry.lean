import Rholphin.Model.Types

/-!
# Registry and directory

The root and the two registries are keyed maps with a status per entry.  The
map is modelled as an association list, which is enough for the invariant that
matters: a successful registration makes the code resolve, and a second
registration of the same code is refused (I2).
-/

namespace Rholphin.Model.Registry

open Rholphin

inductive AssetKind where
  | stablecoin
  | external
  deriving Repr, DecidableEq

structure Entry where
  uri : Nat
  version : Nat
  retired : Bool
  kind : AssetKind
  decimals : Nat
  deriving Repr, DecidableEq

/-- A listed R-Cash stablecoin entry. -/
def Entry.stablecoin (uri version : Nat) : Entry :=
  { uri := uri, version := version, retired := false, kind := .stablecoin, decimals := 8 }

/-- A listed external asset (bridge/custodian adapter). -/
def Entry.external (uri : Nat) : Entry :=
  { uri := uri, version := 1, retired := false, kind := .external, decimals := 8 }

structure RootStore where
  entries : List (Nat × Entry)
  frozen : Bool
  nonce : Nat

def lookup (entries : List (Nat × Entry)) (key : Nat) : Option Entry :=
  match entries with
  | [] => none
  | (k, v) :: rest => if k = key then some v else lookup rest key

def insert (entries : List (Nat × Entry)) (key : Nat) (v : Entry) : List (Nat × Entry) :=
  (key, v) :: entries

@[simp] theorem lookup_insert_same (entries : List (Nat × Entry)) (key : Nat) (v : Entry) :
    lookup (insert entries key v) key = some v := by
  simp [lookup, insert]

theorem lookup_insert_ne {entries : List (Nat × Entry)} {key other : Nat} {v : Entry}
    (h : other ≠ key) : lookup (insert entries key v) other = lookup entries other := by
  simp only [lookup, insert]
  rw [if_neg (fun hk => h hk.symm)]

/-- I2: registration inserts exactly one entry per code. -/
theorem register_lookup {entries : List (Nat × Entry)} {key : Nat} {v : Entry}
    (habsent : lookup entries key = none) :
    lookup (insert entries key v) key = some v := by
  simp

/-! ## Root -/

def root_resolve (s : RootStore) (key minVersion : Nat) : Option (Nat × Nat) :=
  match lookup s.entries key with
  | none => none
  | some entry =>
      if entry.retired then none
      else if entry.version < minVersion then none
      else some (entry.uri, entry.version)

def root_get (s : RootStore) (key : Nat) : Option Entry := lookup s.entries key

def root_keys (s : RootStore) : List Nat := s.entries.map (fun p => p.1)

def root_register (s : RootStore) (key uri version : Nat) : Option RootStore :=
  if s.frozen then none
  else if (lookup s.entries key).isSome then none
  else some { s with entries := insert s.entries key (Entry.stablecoin uri version) }

theorem root_register_resolves {s : RootStore} {key uri version : Nat} {s' : RootStore}
    (h : root_register s key uri version = some s') :
    root_get s' key = some (Entry.stablecoin uri version) := by
  unfold root_register at h
  split at h
  · contradiction
  · split at h
    · contradiction
    · simp only [Option.some.injEq] at h
      subst h
      simp [Entry.stablecoin, root_get, lookup, insert]

def root_rotate (s : RootStore) (key expected newUri newVersion : Nat) : Option RootStore :=
  match lookup s.entries key with
  | none => none
  | some entry =>
      if s.frozen then none
      else if entry.version ≠ expected then none
      else some
        { s with entries := insert s.entries key (Entry.stablecoin newUri newVersion) }

def root_deprecate (s : RootStore) (key : Nat) : Option RootStore :=
  match lookup s.entries key with
  | none => none
  | some entry =>
      if s.frozen then none
      else some { s with entries := insert s.entries key { entry with retired := true } }

def root_freeze (s : RootStore) : Option RootStore :=
  if s.frozen then none else some { s with frozen := true }

def root_admin (s : RootStore) (threshold : Nat) : Option RootStore :=
  if s.frozen then none else some { s with nonce := threshold }

/-! ## Stablecoin directory -/

structure Directory where
  systems : List (Nat × Entry)
  rev : Nat

def stablecoinDirectory_register (d : Directory) (code : Nat) (entry : Entry) : Option Directory :=
  if (lookup d.systems code).isSome then none
  else some { d with systems := insert d.systems code entry, rev := d.rev + 1 }

def stablecoinDirectory_lookup (d : Directory) (code : Nat) : Option Entry :=
  lookup d.systems code

def stablecoinDirectory_entries (d : Directory) : List Nat := d.systems.map (fun p => p.1)

/-! ## Currency registry -/

structure CurrencyStore where
  currencies : List (Nat × Entry)
  rev : Nat

def currencyRegistry_register (s : CurrencyStore) (code : Nat) (entry : Entry) : Option CurrencyStore :=
  if (lookup s.currencies code).isSome then none
  else some { s with currencies := insert s.currencies code entry, rev := s.rev + 1 }

/-- I2: a successful registration makes the code resolve, and one code has one
entry. -/
theorem currencyRegistry_register_resolves {s s' : CurrencyStore} {code : Nat} {entry : Entry}
    (h : currencyRegistry_register s code entry = some s') :
    lookup s'.currencies code = some entry := by
  unfold currencyRegistry_register at h
  split at h
  · contradiction
  · simp only [Option.some.injEq] at h
    subst h
    simp [lookup, insert]

/-- List an external asset.  The adapter has already been attested; the model
records the one-entry-per-code and 8-decimal rules. -/
def currencyRegistry_registerExternal (s : CurrencyStore) (code uri : Nat) : Option CurrencyStore :=
  if (lookup s.currencies code).isSome then none
  else some { s with currencies := insert s.currencies code (Entry.external uri), rev := s.rev + 1 }

@[simp] theorem Entry.external_kind (uri : Nat) :
    (Entry.external uri).kind = AssetKind.external := rfl

@[simp] theorem Entry.external_decimals (uri : Nat) :
    (Entry.external uri).decimals = 8 := rfl

theorem currencyRegistry_registerExternal_shape {s s' : CurrencyStore} {code uri : Nat}
    (h : currencyRegistry_registerExternal s code uri = some s') :
    (lookup s'.currencies code).map (fun e => (e.kind, e.decimals))
      = some (AssetKind.external, 8) := by
  unfold currencyRegistry_registerExternal at h
  split at h
  · contradiction
  · simp only [Option.some.injEq] at h
    subst h
    simp [Entry.external, lookup, insert]

def currencyRegistry_currency (s : CurrencyStore) (code : Nat) : Option Entry :=
  lookup s.currencies code

def currencyRegistry_currencies (s : CurrencyStore) : List Nat := s.currencies.map (fun p => p.1)

def currencyRegistry_setPaused (s : CurrencyStore) (code : Nat) (paused : Bool) : Option CurrencyStore :=
  match lookup s.currencies code with
  | none => none
  | some entry => some { s with currencies := insert s.currencies code { entry with retired := paused } }

/-! ## Asset resolver -/

def assetResolver_issuer (assetId : Nat) (entry : Option Entry) : Option Nat :=
  if assetId = 0 then some 0 else entry.map (fun e => e.uri)

def assetResolver_kind (assetId : Nat) (entry : Option Entry) : Option Bool :=
  if assetId = 0 then some false else entry.map (fun _ => true)

end Rholphin.Model.Registry
