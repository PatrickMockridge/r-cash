//! Typed protocol writes.
//!
//! Every method signs one deploy, waits for it to be processed and final, and returns
//! the decoded reply. A refusal is `ChainError::Refused`; a reverted deploy is
//! `ChainError::DeployFailed`. Both leave the protocol state unchanged.

use rcash_chain::rho_expr::{Reply, RhoValue};
use rcash_chain::ChainError;
use rcash_core::Amount;

use crate::reads::POOL_KEY;
use crate::{terms, Client};

/// The result of an Account arm: the owner id and the arm's reply values.
#[derive(Clone, Debug)]
pub struct TxResult {
    pub owner_id: String,
    pub values: Vec<RhoValue>,
}

/// The swap result.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SwapResult {
    pub amount_out: i64,
    pub fee: i64,
}

impl Client {
    async fn account_tx(&self, term: &str) -> Result<TxResult, ChainError> {
        let value = self.signed_value(term).await?;
        let items = value
            .as_tuple()
            .ok_or_else(|| decode("account reply is not a tuple"))?;
        let owner_id = items
            .first()
            .and_then(RhoValue::as_str)
            .ok_or_else(|| decode("account reply has no owner id"))?
            .to_string();
        Ok(TxResult {
            owner_id,
            values: items[1..].to_vec(),
        })
    }

    /// Fund the Account with REV from the caller's native vault.
    pub async fn deposit_rev(&self, amount: i64) -> Result<Amount, ChainError> {
        let factory = self.require_manifest()?.account_factory_uri.clone();
        let tx = self
            .account_tx(&terms::deposit_rev(&factory, amount))
            .await?;
        let values = reply(&tx.values, 0)?.into_result()?;
        Ok(Amount::raw(int_at(&values, 0)?))
    }

    /// Withdraw REV from the Account to a native REV address.
    pub async fn withdraw_rev_to(&self, amount: i64, address: &str) -> Result<Reply, ChainError> {
        let factory = self.require_manifest()?.account_factory_uri.clone();
        let tx = self
            .account_tx(&terms::withdraw_rev_to(&factory, amount, address)?)
            .await?;
        reply(&tx.values, 0)
    }

    /// Send a claimable transfer. `claim_hash_hex` is the 32-byte BLAKE2b hash of the secret.
    pub async fn send_transfer(
        &self,
        source: &str,
        dest: &str,
        amount: i64,
        min_dest: i64,
        claim_hash_hex: &str,
        expiry_height: i64,
    ) -> Result<i64, ChainError> {
        let factory = self.require_manifest()?.account_factory_uri.clone();
        let call = format!(
            "\"sendTransfer\", *deployerId, {}, {}, {amount}, {min_dest}, {}, {expiry_height}",
            terms::s(source)?,
            terms::s(dest)?,
            rcash_core::rho::hex_bytes(claim_hash_hex)?
        );
        let tx = self
            .account_tx(&terms::account_call(&factory, &call))
            .await?;
        let values = reply(&tx.values, 0)?.into_result()?;
        int_at(&values, 0)
    }

    /// Claim a transfer with its secret.
    pub async fn claim_transfer(
        &self,
        transfer_id: i64,
        dest: &str,
        secret_hex: &str,
    ) -> Result<Amount, ChainError> {
        let factory = self.require_manifest()?.account_factory_uri.clone();
        let call = format!(
            "\"claimTransfer\", {transfer_id}, {}, {}",
            terms::s(dest)?,
            rcash_core::rho::hex_bytes(secret_hex)?
        );
        let tx = self
            .account_tx(&terms::account_call(&factory, &call))
            .await?;
        let values = reply(&tx.values, 0)?.into_result()?;
        Ok(Amount::raw(int_at(&values, 0)?))
    }

    /// Refund an expired transfer into this Account.
    pub async fn refund_transfer(
        &self,
        transfer_id: i64,
        dest: &str,
    ) -> Result<Amount, ChainError> {
        let factory = self.require_manifest()?.account_factory_uri.clone();
        let call = format!(
            "\"refundTransfer\", *deployerId, {transfer_id}, {}",
            terms::s(dest)?
        );
        let tx = self
            .account_tx(&terms::account_call(&factory, &call))
            .await?;
        let values = reply(&tx.values, 0)?.into_result()?;
        Ok(Amount::raw(int_at(&values, 0)?))
    }

    /// Add liquidity from the Account; returns the shares minted.
    pub async fn add_liquidity(
        &self,
        base_amount: i64,
        quote_amount: i64,
        min_shares: i64,
    ) -> Result<i64, ChainError> {
        let manifest = self.require_manifest()?;
        let components = manifest.components_uri.clone();
        let factory = manifest.account_factory_uri.clone();
        let term = terms::add_liquidity(
            &components,
            &factory,
            POOL_KEY,
            base_amount,
            quote_amount,
            min_shares,
        )?;
        let tx = self.account_tx(&term).await?;
        let shares = tx
            .values
            .first()
            .and_then(RhoValue::as_int)
            .ok_or_else(|| decode("add liquidity did not return shares"))?;
        // The LP deposit reply is values[1]; surface a refusal if it failed.
        reply(&tx.values, 1)?.into_result()?;
        Ok(shares)
    }

    /// Remove liquidity; returns the shares burned.
    pub async fn remove_liquidity(
        &self,
        shares: i64,
        min_base: i64,
        min_quote: i64,
    ) -> Result<i64, ChainError> {
        let manifest = self.require_manifest()?;
        let components = manifest.components_uri.clone();
        let factory = manifest.account_factory_uri.clone();
        let term =
            terms::remove_liquidity(&components, &factory, POOL_KEY, shares, min_base, min_quote)?;
        let tx = self.account_tx(&term).await?;
        let burned = tx
            .values
            .first()
            .and_then(RhoValue::as_int)
            .ok_or_else(|| decode("remove liquidity did not return shares"))?;
        reply(&tx.values, 1)?.into_result()?;
        reply(&tx.values, 2)?.into_result()?;
        Ok(burned)
    }

    /// Swap through the corridor pool. `source` is withdrawn and `dest` deposited.
    pub async fn swap(
        &self,
        source: &str,
        dest: &str,
        amount: i64,
        min_out: i64,
    ) -> Result<SwapResult, ChainError> {
        let manifest = self.require_manifest()?;
        let components = manifest.components_uri.clone();
        let factory = manifest.account_factory_uri.clone();
        let term = terms::swap(
            &components,
            &factory,
            POOL_KEY,
            source,
            dest,
            amount,
            min_out,
        )?;
        let tx = self.account_tx(&term).await?;
        let amount_out = tx
            .values
            .first()
            .and_then(RhoValue::as_int)
            .ok_or_else(|| decode("swap did not return an output amount"))?;
        let fee = tx
            .values
            .get(1)
            .and_then(RhoValue::as_int)
            .ok_or_else(|| decode("swap did not return a fee"))?;
        reply(&tx.values, 2)?.into_result()?;
        Ok(SwapResult { amount_out, fee })
    }

    /// Convert one local currency to another: the same single-deploy composition as `swap`.
    pub async fn convert(
        &self,
        source: &str,
        dest: &str,
        amount: i64,
        min_out: i64,
    ) -> Result<SwapResult, ChainError> {
        self.swap(source, dest, amount, min_out).await
    }

    /// Submit a signed reporter price. The reporter key signs the canonical payload off-chain.
    pub async fn oracle_submit(
        &self,
        currency: &str,
        price: i64,
        height: i64,
        index: i64,
        public_hex: &str,
        signature_hex: &str,
    ) -> Result<Reply, ChainError> {
        let oracle = self.require_manifest()?.oracle_uri.clone();
        let term = terms::oracle_submit(
            &oracle,
            currency,
            price,
            height,
            index,
            public_hex,
            signature_hex,
        )?;
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)
    }

    /// A generic M-of-N admin action against a component URI.
    ///
    /// `args_term` and `sigs_term` are pre-rendered Rholang values produced by the caller
    /// from typed values (the CLI's admin signer); they are not user free text.
    pub async fn admin_action(
        &self,
        uri: &rcash_core::assets::RegistryUri,
        nonce: i64,
        action: &str,
        args_term: &str,
        sigs_term: &str,
    ) -> Result<Reply, ChainError> {
        let term = terms::admin_action(uri, nonce, action, args_term, sigs_term)?;
        let value = self.signed_value(&term).await?;
        Reply::from_value(&value)
    }
}

fn reply(values: &[RhoValue], index: usize) -> Result<Reply, ChainError> {
    let value = values
        .get(index)
        .ok_or_else(|| decode(format!("reply {index} is missing")))?;
    Reply::from_value(value)
}

fn decode(message: impl Into<String>) -> ChainError {
    ChainError::Decode(message.into())
}

fn int_at(values: &[RhoValue], index: usize) -> Result<i64, ChainError> {
    values
        .get(index)
        .and_then(RhoValue::as_int)
        .ok_or_else(|| decode(format!("value {index} is not an integer")))
}
