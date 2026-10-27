import Rholphin.Basic

/-!
# Floor and ceiling division

The deploy sources use two divisions: `n / d` and `(n + d - 1) / d`.  Every
economic guard and payout is stated in terms of one of them.  These lemmas are
the only bridge between the two, and they are used by the issuer, savings, PSM
and AMM modules.
-/

namespace Rholphin

/-- Exact characterisation of floor division, for `d > 0`. -/
theorem floorDiv_eq_iff {n d k : Nat} (hd : 0 < d) :
    floorDiv n d = k ↔ k * d ≤ n ∧ n < (k + 1) * d := by
  unfold floorDiv
  constructor
  · intro h
    constructor
    · rw [← h]
      simpa [Nat.mul_comm] using Nat.mul_div_le n d
    · -- `n / d < k + 1` and the multiplication form of the division bound
      have hlt : n / d < k + 1 := by rw [h]; exact Nat.lt_succ_self k
      have := (Nat.div_lt_iff_lt_mul (k := d) (x := n) (y := k + 1) hd).mp hlt
      simpa [Nat.succ_mul] using this
  · rintro ⟨hlo, hhi⟩
    exact Nat.div_eq_of_lt_le hlo hhi

/-- Floor division never exceeds the dividend. -/
theorem floorDiv_le (n d : Nat) : floorDiv n d ≤ n := Nat.div_le_self n d

/-- `k * d ≤ floorDiv n d * d ≤ n`. -/
theorem floorDiv_mul_le (n d : Nat) : d * floorDiv n d ≤ n := Nat.mul_div_le n d

/-- The ceiling is the least `k` with `n ≤ k * d`. -/
theorem ceilDiv_le_iff {n d k : Nat} (hd : 0 < d) :
    ceilDiv n d ≤ k ↔ n ≤ k * d := by
  unfold ceilDiv
  rw [← Nat.lt_succ_iff,
      Nat.div_lt_iff_lt_mul (k := d) (x := n + d - 1) (y := k + 1) hd,
      Nat.succ_mul]
  omega

/-- The ceiling reaches the dividend: `n ≤ d * ceilDiv n d`. -/
theorem ceilDiv_ge {n d : Nat} (hd : 0 < d) : n ≤ d * ceilDiv n d := by
  have := (ceilDiv_le_iff (n := n) (d := d) (k := ceilDiv n d) hd).mp (Nat.le_refl _)
  simpa [Nat.mul_comm] using this

/-- The ceiling is positive iff the dividend is. -/
theorem ceilDiv_pos {n d : Nat} (hd : 0 < d) : 0 < ceilDiv n d ↔ 0 < n := by
  constructor
  · intro h
    cases Nat.eq_zero_or_pos n with
    | inl hn =>
        subst hn
        unfold ceilDiv at h
        rw [Nat.zero_add, Nat.div_eq_of_lt (Nat.sub_lt hd (by decide))] at h
        exact absurd h (Nat.lt_irrefl 0)
    | inr hp => exact hp
  · intro hn
    cases Nat.eq_zero_or_pos (ceilDiv n d) with
    | inl hz =>
        have hge := ceilDiv_ge (n := n) (d := d) hd
        rw [hz] at hge
        simp at hge
        omega
    | inr hp => exact hp

/-- `ceilDiv` is monotone in the dividend. -/
theorem ceilDiv_mono {n m d : Nat} (hd : 0 < d) (h : n ≤ m) :
    ceilDiv n d ≤ ceilDiv m d := by
  rw [ceilDiv_le_iff hd]
  exact Nat.le_trans h (by simpa [Nat.mul_comm] using ceilDiv_ge (n := m) (d := d) hd)

/-- A fee rounded up never exceeds the gross amount when the rate is at most
10000 bps. -/
theorem ceilDiv_le_self {n b d : Nat} (hd : 0 < d) (hb : b ≤ d) :
    ceilDiv (n * b) d ≤ n := by
  rw [ceilDiv_le_iff hd]
  calc
    n * b ≤ n * d := Nat.mul_le_mul_left n hb
    _ = n * d := rfl
    _ = n * d := rfl

/-- Division by a fixed positive divisor is monotone in the dividend. -/
theorem div_le_div_of_le_left {a b c : Nat} (h : a ≤ b) : a / c ≤ b / c := by
  by_cases hc : c = 0
  · subst hc
    simp
  · have hcpos : 0 < c := Nat.pos_of_ne_zero hc
    rw [Nat.le_div_iff_mul_le (k := c) (x := a / c) (y := b) hcpos]
    exact Nat.le_trans (Nat.div_mul_le_self a c) h

/-- The canonical interest step: `debt + ceil(debt * rate * blocks / 1e12)`. -/
theorem ceilDiv_add_le (n d : Nat) (hd : 0 < d) : ceilDiv n d + 1 ≤ n + d := by
  unfold ceilDiv
  have h1 : (n + d - 1) / d ≤ (n + d - 1) := Nat.div_le_self _ _
  omega

end Rholphin
