import Rholphin.Linear.Cell
import Rholphin.Linear.Protocol
import Rholphin.Invariants
import Rholphin.Model.Registry
import Rholphin.Model.Transfer
import Rholphin.Model.Market
import Rholphin.Model.Pool
import Rholphin.Model.Governance
import Rholphin.Model.Oracle
import Rholphin.Model.Identity
import Rholphin.Model.Kernel

/-!
# Axiom audit

`#print axioms` is run for every main theorem.  The gate script rejects any
output containing `sorryAx` or a project-local axiom.
-/

#print axioms Rholphin.ceilDiv_le_iff
#print axioms Rholphin.ceilDiv_mono
#print axioms Rholphin.accrue_mono_height
#print axioms Rholphin.close_factor_bound
#print axioms Rholphin.valueOf_le_assets
#print axioms Rholphin.fee_le_gross
#print axioms Rholphin.outB2Q_le
#print axioms Rholphin.peek_then_put_rejected
#print axioms Rholphin.take_without_put_not_wf
#print axioms Rholphin.nested_call_rejected
#print axioms Rholphin.h2a_caller_token
#print axioms Rholphin.Model.Issuer.repay_S3
#print axioms Rholphin.Model.Issuer.writeOff_S3
#print axioms Rholphin.Model.Vault.deposit_S2
#print axioms Rholphin.Model.Vault.mint_S2
#print axioms Rholphin.Model.BufferSavings.deposit_S10
#print axioms Rholphin.Model.BufferSavings.withdraw_S10
#print axioms Rholphin.Model.Psm.sell_floor
#print axioms Rholphin.Invariants.S9_waterfall_le
#print axioms Rholphin.Invariants.S7_settle_S1
#print axioms Rholphin.Invariants.S6_writeOff_badDebt
#print axioms Rholphin.Invariants.S12_not_early
#print axioms Rholphin.Model.Registry.currencyRegistry_register_resolves
#print axioms Rholphin.Model.Registry.Entry.external_decimals
#print axioms Rholphin.Model.Registry.currencyRegistry_registerExternal_shape
#print axioms Rholphin.Model.Transfer.claim_then_refund_refused
#print axioms Rholphin.Model.Market.staged_is_draft
#print axioms Rholphin.Model.Market.pauseAsset_singleton
#print axioms Rholphin.Model.Market.pauseAsset_pauses_all
#print axioms Rholphin.Model.Market.stage_writes_both
#print axioms Rholphin.Model.Market.stage_refuses_active
#print axioms Rholphin.Model.Market.delisted_accepts_nothing
#print axioms Rholphin.Model.Pool.fund_refuses_short
#print axioms Rholphin.Model.Governance.execute_not_early
#print axioms Rholphin.Model.Oracle.activate_requires_trial
#print axioms Rholphin.Model.Identity.getOrCreate_verify
#print axioms Rholphin.Model.Identity.gate_other
