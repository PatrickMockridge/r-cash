import Rholphin.Linear.Cell
import Rholphin.Linear.Protocol
import Rholphin.Linear.Prim
import Rholphin.Linear.Deploy
import Rholphin.Linear.Serial
import Rholphin.Linear.Interleave
import Rholphin.Linear.Prov
import Rholphin.Linear.Provisioning
import Rholphin.Prim.EDSL
import Rholphin.Crypto.Hash
import Rholphin.Crypto.Sig
import Rholphin.Crypto.Claim
import Rholphin.Crypto.Codec
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
#print axioms Rholphin.runPrim_cell
#print axioms Rholphin.CellArm.preserves
#print axioms Rholphin.Linear.caller_never_stored
#print axioms Rholphin.Linear.authority_use_requires_provenance
#print axioms Rholphin.Linear.bundle_no_registry_cap
#print axioms Rholphin.Linear.facet_store_scope
#print axioms Rholphin.Linear.facet_store_rejects_foreign_kind
#print axioms Rholphin.Linear.facet_store_rejects_foreign_auth
#print axioms Rholphin.Linear.mint_facet_cannot_store_burn_auth
#print axioms Rholphin.Linear.burn_facet_cannot_store_mint_auth
#print axioms Rholphin.Linear.burn_facet_call_carries_payment
#print axioms Rholphin.Linear.settle_facet_call_carries_payment
#print axioms Rholphin.Linear.custody_deposit_carries_payment
#print axioms Rholphin.Linear.buffer_deposit_carries_payment
#print axioms Rholphin.Linear.mint_facet_call_carries_no_payment
#print axioms Rholphin.Linear.allowed_arm_has_kind
#print axioms Rholphin.Linear.nonce_cannot_provision_twice
#print axioms Rholphin.Linear.provision_requires_pinned_shop
#print axioms Rholphin.Linear.issuer_shop_cannot_issue_buffer
#print axioms Rholphin.Linear.buffer_shop_cannot_issue_mint
#print axioms Rholphin.Linear.provision_refusal_rolls_back
#print axioms Rholphin.Linear.provision_returns_no_cap
#print axioms Rholphin.Linear.provision_routes_facets_to_consumer
#print axioms Rholphin.Linear.forged_facet_refused
#print axioms Rholphin.Linear.issued_facet_accepted
#print axioms Rholphin.Linear.slot_write_once
#print axioms Rholphin.Linear.rotation_preserves_facet
#print axioms Rholphin.Linear.rotation_refuses_old
#print axioms Rholphin.Linear.rotation_accepts_new
#print axioms Rholphin.Linear.rotation_other_cell
#print axioms Rholphin.Linear.rotation_requires_governor
#print axioms Rholphin.Linear.authorized_rotation_keeps_facet
#print axioms Rholphin.Linear.authorized_domain_action
#print axioms Rholphin.Linear.authorized_rotation_refuses_old
#print axioms Rholphin.Linear.authorized_rotation_accepts_new
#print axioms Rholphin.Linear.mint_consumer_refuses_recapitalise
#print axioms Rholphin.Linear.mint_consumer_recap_pre_effect
#print axioms Rholphin.Linear.vault_accept_slot_write_once
#print axioms Rholphin.Linear.call_target_is_not_vault_accept
#print axioms Rholphin.Linear.auth_set_counts
#print axioms Rholphin.Linear.auth_domains_nodup
#print axioms Rholphin.Linear.settlement_interest_routes_to_buffer
#print axioms Rholphin.Linear.settlement_clean_routes_nothing
#print axioms Rholphin.Linear.settlement_return_shape
#print axioms Rholphin.take_put_balance
#print axioms Rholphin.refuse_quiescent
#print axioms Rholphin.fail_aborts
#print axioms Rholphin.commit_atomic
#print axioms Rholphin.apply_preserves_untouched
#print axioms Rholphin.apply_bumps_rev
#print axioms Rholphin.step_preserves_linear
#print axioms Rholphin.held_take_unavailable
#print axioms Rholphin.steps_preserve_linear
#print axioms Rholphin.terms_put_integrity
#print axioms Rholphin.terms_put_rejects_mismatch
#print axioms Rholphin.hash_distinct
#print axioms Rholphin.verify_true_implies_signer
#print axioms Rholphin.authorized_imp_signer
#print axioms Rholphin.claim_requires_preimage
#print axioms Rholphin.wrong_secret_refused
#print axioms Rholphin.claim_secret_unique
#print axioms Rholphin.codec_no_pipe_collision
#print axioms Rholphin.codec_injective
#print axioms Rholphin.Model.Issuer.repay_S3
#print axioms Rholphin.Model.Issuer.writeOff_S3
#print axioms Rholphin.Model.Issuer.settle_principal
#print axioms Rholphin.Model.Issuer.settle_S1
#print axioms Rholphin.Model.Vault.deposit_S2
#print axioms Rholphin.Model.Vault.mint_S2
#print axioms Rholphin.Model.BufferSavings.deposit_S10
#print axioms Rholphin.Model.BufferSavings.withdraw_S10
#print axioms Rholphin.Model.BufferSavings.cover_surplus_le
#print axioms Rholphin.Model.BufferSavings.paySavings_le
#print axioms Rholphin.Model.BufferSavings.waterfall_le
#print axioms Rholphin.Model.Psm.sell_floor
#print axioms Rholphin.Model.Psm.buyChecked_ceiling
#print axioms Rholphin.Model.Psm.buyChecked_adds
#print axioms Rholphin.Model.Psm.buyChecked_refuses_negative
#print axioms Rholphin.Model.Psm.sellChecked_floor
#print axioms Rholphin.Model.Psm.sellChecked_subtracts
#print axioms Rholphin.Model.Psm.sellChecked_refuses_below_floor
#print axioms Rholphin.Model.BufferSavings.notifyChecked_refuses_zero
#print axioms Rholphin.Model.BufferSavings.notifyChecked_preserves_S10
#print axioms Rholphin.health_iff_maxDebt
#print axioms Rholphin.Model.Vault.mintChecked_preserves_health
#print axioms Rholphin.Model.Vault.mintChecked_refuses_unhealthy
#print axioms Rholphin.Model.Vault.withdrawChecked_preserves_health
#print axioms Rholphin.Model.Vault.withdrawChecked_refuses_unhealthy
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
#print axioms Rholphin.Model.Market.admit_active
#print axioms Rholphin.Model.Market.admit_fresh
#print axioms Rholphin.Model.Market.admit_min_ticket
#print axioms Rholphin.Model.Market.admit_max_trade
#print axioms Rholphin.Model.Market.stage_writes_both
#print axioms Rholphin.Model.Market.stage_refuses_active
#print axioms Rholphin.Model.Market.marketTerms_putChecked_refuses_bad_sponsor
#print axioms Rholphin.Model.Market.marketTerms_putChecked_integrity
#print axioms Rholphin.Model.Market.delisted_accepts_nothing
#print axioms Rholphin.Model.Pool.fund_refuses_short
#print axioms Rholphin.Model.Pool.fxPool_attest_sound
#print axioms Rholphin.Model.Pool.empty_ledger
#print axioms Rholphin.Model.Pool.mintShares_preserves_ledger
#print axioms Rholphin.Model.Pool.burnShares_preserves_ledger
#print axioms Rholphin.Model.Pool.fund_sets_funded
#print axioms Rholphin.Model.Pool.fund_refuses_funded
#print axioms Rholphin.Model.Pool.release_then_cancel_refused
#print axioms Rholphin.Model.Pool.cancel_then_release_refused
#print axioms Rholphin.Model.Governance.execute_not_early
#print axioms Rholphin.Model.Oracle.activate_requires_trial
#print axioms Rholphin.Model.Oracle.reportersOk_nodup
#print axioms Rholphin.Model.Oracle.reportersOk_length
#print axioms Rholphin.Model.Oracle.reportersOk_sponsor
#print axioms Rholphin.Model.Oracle.stale_pair_refused
#print axioms Rholphin.Model.Oracle.pair_rate_ages
#print axioms Rholphin.Model.Market.bind_preserves_directory
#print axioms Rholphin.Model.Market.seal_preserves_directory
#print axioms Rholphin.Model.Registry.registerListed_refuses_no_root
#print axioms Rholphin.Model.Registry.registerListed_preserves_S8
#print axioms Rholphin.reject_no_effect
#print axioms Rholphin.preOk_disjoint
#print axioms Rholphin.commit_disjoint_does_not_block
#print axioms Rholphin.apply_disjoint_values
#print axioms Rholphin.Model.Identity.getOrCreate_verify
#print axioms Rholphin.Model.Identity.gate_other
