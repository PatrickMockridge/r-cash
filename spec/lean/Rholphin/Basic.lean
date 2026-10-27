/-!
# Basic quantities

All amounts are integers in the smallest unit of the asset.  The Rholang
contracts use `Nat`-style unsigned integers with truncating subtraction; the
model makes every subtraction total by carrying side conditions (`a ≤ b`) where
the contract guard supplies them.

`E8` and `E12` are the price and interest scales used by the deploy sources.
-/

namespace Rholphin

abbrev Amount := Nat

/-- Price and rate scale: 1e8. -/
abbrev E8 : Nat := 100000000

/-- Interest scale: 1e12. -/
abbrev E12 : Nat := 1000000000000

/-- Basis-point scale. -/
abbrev Bps : Nat := 10000

/-- Truncating division, the Rholang `/` on naturals. -/
def floorDiv (n d : Nat) : Nat := n / d

/-- Division rounded up, the `(n + d - 1) / d` form used by every fee and
interest arm.  `ceilDiv n 0` is `0` by Lean's division convention and is never
reached: every caller guards `d > 0`. -/
def ceilDiv (n d : Nat) : Nat := (n + d - 1) / d

/-- A signed balance: `psmDebt` and any AMM term that can be negative. -/
abbrev Signed := Int

end Rholphin
