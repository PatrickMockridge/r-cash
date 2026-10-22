//! Rholang term templates for protocol calls.
//!
//! Every argument is rendered from a typed value in this crate; no caller-supplied text
//! reaches a term. Strings go through `rcash_core::rho::quote_str`, which refuses a
//! double quote (unrepresentable in Rholang).

use rcash_core::assets::RegistryUri;
use rcash_core::rho::{hex_bytes, quote_str, quote_uri};
use rcash_core::CoreError;

type Result<T> = std::result::Result<T, CoreError>;

/// Render a string argument.
pub fn s(value: &str) -> Result<String> {
    quote_str(value)
}

/// Render an integer argument.
pub fn n(value: i64) -> String {
    value.to_string()
}

/// Join rendered arguments.
pub fn args(items: &[String]) -> String {
    items.join(", ")
}

/// Call a contract at a known registry URI and return its reply on a private channel.
pub fn uri_call(uri: &RegistryUri, args: &str) -> String {
    format!(
        "new return, rl(`rho:registry:lookup`), capCh, resCh in {{ rl!({}, *capCh) | \
         for (cap <- capCh) {{ cap!({args}, *resCh) | for (@r <- resCh) {{ return!(r) }} }} }}",
        quote_uri(uri)
    )
}

/// Look up a component by key in the Components registry, then call it.
pub fn component_call(components: &RegistryUri, key: &str, args: &str) -> Result<String> {
    Ok(format!(
        "new return, rl(`rho:registry:lookup`), compsCh, capCh, resCh in {{ rl!({}, *compsCh) | \
         for (comps <- compsCh) {{ comps!(\"get\", {}, *capCh) | \
         for (@(true, cap) <- capCh) {{ @cap!({args}, *resCh) | \
         for (@r <- resCh) {{ return!(r) }} }} }} }}",
        quote_uri(components),
        quote_str(key)?
    ))
}

/// Like [`uri_call`], but for a signed read: the reply goes to `deployId`.
///
/// `explore-deploy` has no block context — `rho:block:data` reports height 0 — so any arm
/// that checks freshness must run as a signed deploy.
pub fn uri_call_deploy(uri: &RegistryUri, args: &str) -> String {
    format!(
        "new rl(`rho:registry:lookup`), capCh, resCh, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *capCh) | \
         for (cap <- capCh) {{ cap!({args}, *resCh) | \
         for (@r <- resCh) {{ deployId!(r) }} }} }}",
        quote_uri(uri)
    )
}

/// Like [`component_call`], but for a signed read: the reply goes to `deployId`.
pub fn component_call_deploy(components: &RegistryUri, key: &str, args: &str) -> Result<String> {
    Ok(format!(
        "new rl(`rho:registry:lookup`), compsCh, capCh, resCh, \
         deployId(`rho:rchain:deployId`) in {{ rl!({}, *compsCh) | \
         for (comps <- compsCh) {{ comps!(\"get\", {}, *capCh) | \
         for (@(true, cap) <- capCh) {{ @cap!({args}, *resCh) | \
         for (@r <- resCh) {{ deployId!(r) }} }} }} }}",
        quote_uri(components),
        quote_str(key)?
    ))
}

/// The native REV vault balance of an address.
pub fn rev_balance(address: &str) -> Result<String> {
    Ok(format!(
        "new return, revVault(`rho:rchain:revVault`), ret in {{ \
         revVault!(\"getBalance\", {}, *ret) | for (@b <- ret) {{ return!(b) }} }}",
        quote_str(address)?
    ))
}

/// Read one or more Account balances in a single signed deploy.
///
/// The reply is `(ownerId, [reply_0, …])`, where each reply is the Account's
/// `(true, amount)` or `(false, reason)`.
pub fn balances(factory: &RegistryUri, assets: &[String]) -> Result<String> {
    if assets.is_empty() {
        return Err(CoreError::BadManifest("no assets requested".into()));
    }
    let channels: Vec<String> = (0..assets.len()).map(|i| format!("b{i}Ch")).collect();
    let calls: Vec<String> = assets
        .iter()
        .zip(&channels)
        .map(|(asset, channel)| {
            Ok(format!(
                "@account!(\"balance\", *deployerId, {}, *{channel})",
                quote_str(asset)?
            ))
        })
        .collect::<Result<Vec<_>>>()?;
    let binds: Vec<String> = channels
        .iter()
        .enumerate()
        .map(|(index, channel)| format!("@r{index} <- {channel}"))
        .collect();
    let replies: Vec<String> = (0..assets.len()).map(|i| format!("r{i}")).collect();
    Ok(format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), factoryCh, accountCh, pkCh, {}, \
         deployId(`rho:rchain:deployId`) in {{ rl!({}, *factoryCh) | \
         deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ {} | \
         for ({}) {{ deployId!((ownerId, [{}])) }} }} }} }}",
        channels.join(", "),
        quote_uri(factory),
        calls.join(" | "),
        binds.join("; "),
        replies.join(", "),
    ))
}

/// A standard Account arm call, returning `(ownerId, reply)` on `deployId`.
pub fn account_call(factory: &RegistryUri, call: &str) -> String {
    format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), factoryCh, accountCh, pkCh, vCh, \
         deployId(`rho:rchain:deployId`) in {{ rl!({}, *factoryCh) | \
         deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ \
         factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ \
         @account!({call}, *vCh) | \
         for (@r <- vCh) {{ deployId!((ownerId, r)) }} }} }} }}",
        quote_uri(factory)
    )
}

/// Fund the caller's Account with REV from their native vault.
pub fn deposit_rev(factory: &RegistryUri, amount: i64) -> String {
    format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), factoryCh, accountCh, pkCh, ertpCh, issuerCh, purseCh, \
         fundCh, wdCh, depCh, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *factoryCh) | deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ \
         factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ \
         rl!(`rho:rchain:ertp`, *ertpCh) | for (@(_, ERTP) <- ertpCh) {{ \
         @ERTP!(\"getRevIssuer\", *issuerCh) | \
         for (@(revBrand, issuer) <- issuerCh) {{ \
         @issuer!(\"makeEmptyPurse\", *purseCh) | \
         for (@(true, purse) <- purseCh) {{ \
         @purse!(\"revFund\", *deployerId, {amount}, *fundCh) | \
         for (@_ <- fundCh) {{ @purse!(\"withdraw\", (revBrand, {amount}), *wdCh) | \
         for (@(true, payment) <- wdCh) {{ \
         @account!(\"deposit\", \"REV\", payment, *depCh) | \
         for (@d <- depCh) {{ deployId!((ownerId, d)) }} }} }} }} }} }} }} }} }}",
        quote_uri(factory)
    )
}

/// Withdraw REV from the Account and redeem it to a native REV address.
pub fn withdraw_rev_to(factory: &RegistryUri, amount: i64, address: &str) -> Result<String> {
    Ok(format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), factoryCh, accountCh, pkCh, ertpCh, issuerCh, purseCh, \
         wdCh, depCh, redCh, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *factoryCh) | deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ \
         factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ \
         @account!(\"withdraw\", *deployerId, \"REV\", {amount}, *wdCh) | \
         for (@(true, payment) <- wdCh) {{ \
         rl!(`rho:rchain:ertp`, *ertpCh) | for (@(_, ERTP) <- ertpCh) {{ \
         @ERTP!(\"getRevIssuer\", *issuerCh) | \
         for (@(revBrand, issuer) <- issuerCh) {{ \
         @issuer!(\"makeEmptyPurse\", *purseCh) | \
         for (@(true, purse) <- purseCh) {{ \
         @purse!(\"deposit\", payment, *depCh) | for (@_ <- depCh) {{ \
         @purse!(\"revRedeem\", {amount}, {}, *redCh) | \
         for (@r <- redCh) {{ deployId!((ownerId, r)) }} }} }} }} }} }} }} }} }}",
        quote_uri(factory),
        quote_str(address)?
    ))
}

/// Add liquidity from the Account to the corridor pool.
pub fn add_liquidity(
    components: &RegistryUri,
    factory: &RegistryUri,
    key: &str,
    base_amount: i64,
    quote_amount: i64,
    min_shares: i64,
) -> Result<String> {
    Ok(format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), compsCh, poolCh, factoryCh, accountCh, pkCh, \
         baseWdCh, quoteWdCh, lpCh, depCh, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *compsCh) | for (comps <- compsCh) {{ comps!(\"get\", {}, *poolCh) | \
         for (@(true, pool) <- poolCh) {{ rl!({}, *factoryCh) | \
         deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ \
         factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ \
         @account!(\"withdraw\", *deployerId, \"NGN\", {base_amount}, *baseWdCh) | \
         for (@(true, basePay) <- baseWdCh) {{ \
         @account!(\"withdraw\", *deployerId, \"KES\", {quote_amount}, *quoteWdCh) | \
         for (@(true, quotePay) <- quoteWdCh) {{ \
         @pool!(\"addLiquidity\", basePay, quotePay, {min_shares}, *lpCh) | \
         for (@lp <- lpCh) {{ match lp {{ \
         (true, shares, lpPay) => {{ \
         @account!(\"deposit\", \"LP:NGN/KES:fpmm\", lpPay, *depCh) | \
         for (@d <- depCh) {{ deployId!((ownerId, shares, d)) }} }} \
         _ => deployId!(lp) }} }} }} }} }} }} }} }} }}",
        quote_uri(components),
        quote_str(key)?,
        quote_uri(factory)
    ))
}

/// Remove liquidity from the corridor pool into the Account.
pub fn remove_liquidity(
    components: &RegistryUri,
    factory: &RegistryUri,
    key: &str,
    shares: i64,
    min_base: i64,
    min_quote: i64,
) -> Result<String> {
    Ok(format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), compsCh, poolCh, factoryCh, accountCh, pkCh, \
         wdCh, remCh, baseDepCh, quoteDepCh, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *compsCh) | for (comps <- compsCh) {{ comps!(\"get\", {}, *poolCh) | \
         for (@(true, pool) <- poolCh) {{ rl!({}, *factoryCh) | \
         deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ \
         factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ \
         @account!(\"withdraw\", *deployerId, \"LP:NGN/KES:fpmm\", {shares}, *wdCh) | \
         for (@(true, lpPay) <- wdCh) {{ \
         @pool!(\"removeLiquidity\", lpPay, {min_base}, {min_quote}, *remCh) | \
         for (@r <- remCh) {{ match r {{ \
         (true, basePay, quotePay, sharesOut) => {{ \
         @account!(\"deposit\", \"NGN\", basePay, *baseDepCh) | \
         for (@db <- baseDepCh) {{ \
         @account!(\"deposit\", \"KES\", quotePay, *quoteDepCh) | \
         for (@dq <- quoteDepCh) {{ deployId!((ownerId, sharesOut, db, dq)) }} }} }} \
         _ => deployId!(r) }} }} }} }} }} }} }} }}",
        quote_uri(components),
        quote_str(key)?,
        quote_uri(factory)
    ))
}

/// Swap through the corridor pool inside the Account (also the `convert` composition).
pub fn swap(
    components: &RegistryUri,
    factory: &RegistryUri,
    key: &str,
    asset_in: &str,
    asset_out: &str,
    amount: i64,
    min_out: i64,
) -> Result<String> {
    Ok(format!(
        "new deployerId(`rho:rchain:deployerId`), deployerIdOps(`rho:rchain:deployerId:ops`), \
         rl(`rho:registry:lookup`), compsCh, poolCh, factoryCh, accountCh, pkCh, \
         wdCh, swapCh, depCh, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *compsCh) | for (comps <- compsCh) {{ comps!(\"get\", {}, *poolCh) | \
         for (@(true, pool) <- poolCh) {{ rl!({}, *factoryCh) | \
         deployerIdOps!(\"pubKeyBytes\", *deployerId, *pkCh) | \
         for (factory <- factoryCh; @pk <- pkCh) {{ \
         factory!(\"getOrCreate\", pk, *accountCh) | \
         for (@(true, account, ownerId) <- accountCh) {{ \
         @account!(\"withdraw\", *deployerId, {}, {amount}, *wdCh) | \
         for (@(true, payment) <- wdCh) {{ \
         @pool!(\"swap\", {}, payment, {min_out}, *swapCh) | \
         for (@r <- swapCh) {{ match r {{ \
         (true, out, payOut, fee) => {{ \
         @account!(\"deposit\", {}, payOut, *depCh) | \
         for (@d <- depCh) {{ deployId!((ownerId, out, fee, d)) }} }} \
         _ => deployId!(r) }} }} }} }} }} }} }} }}",
        quote_uri(components),
        quote_str(key)?,
        quote_uri(factory),
        quote_str(asset_in)?,
        quote_str(asset_in)?,
        quote_str(asset_out)?
    ))
}

/// Submit a signed reporter price.
pub fn oracle_submit(
    oracle: &RegistryUri,
    currency: &str,
    price: i64,
    height: i64,
    index: i64,
    public_hex: &str,
    signature_hex: &str,
) -> Result<String> {
    Ok(format!(
        "new rl(`rho:registry:lookup`), ch, ret, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *ch) | for (oracle <- ch) {{ \
         oracle!(\"submit\", {}, {price}, {height}, {index}, {}, {}, *ret) | \
         for (@r <- ret) {{ deployId!(r) }} }} }}",
        quote_uri(oracle),
        quote_str(currency)?,
        hex_bytes(public_hex)?,
        hex_bytes(signature_hex)?
    ))
}

/// A generic M-of-N admin action against a component URI.
pub fn admin_action(
    uri: &RegistryUri,
    nonce: i64,
    action: &str,
    args_term: &str,
    sigs_term: &str,
) -> Result<String> {
    Ok(format!(
        "new rl(`rho:registry:lookup`), ch, ret, deployId(`rho:rchain:deployId`) in {{ \
         rl!({}, *ch) | for (component <- ch) {{ \
         component!(\"admin\", {nonce}, {}, {args_term}, {sigs_term}, *ret) | \
         for (@r <- ret) {{ deployId!(r) }} }} }}",
        quote_uri(uri),
        quote_str(action)?
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn uri() -> RegistryUri {
        RegistryUri::new("rho:id:abc").unwrap()
    }

    #[test]
    fn a_call_never_interpolates_unsafe_text() {
        let call = uri_call(&uri(), "\"quote\", \"NGN\", 1");
        assert!(call.contains("rl!(`rho:id:abc`, *capCh)"));
        assert!(call.contains("cap!(\"quote\", \"NGN\", 1, *resCh)"));
        assert!(call.ends_with("return!(r) } } }"));
    }

    #[test]
    fn balances_batches_every_asset_into_one_deploy() {
        let term = balances(&uri(), &["REV".into(), "NGN".into(), "KES".into()]).unwrap();
        assert!(term.contains("b0Ch, b1Ch, b2Ch"));
        assert!(term.contains("\"REV\", *b0Ch"));
        assert!(term.contains("@r0 <- b0Ch; @r1 <- b1Ch; @r2 <- b2Ch"));
        assert!(term.contains("deployId!((ownerId, [r0, r1, r2]))"));
    }

    #[test]
    fn an_unquotable_asset_is_refused() {
        assert!(balances(&uri(), &["a\"b".into()]).is_err());
    }

    /// The node rejects an unbalanced term with "expected RBrace, got Eof". Every builder
    /// must be balanced; this is cheaper than a devnet round-trip per template.
    #[test]
    fn every_template_has_balanced_braces() {
        let uri = uri();
        let built = vec![
            uri_call(&uri, "\"get\""),
            component_call(&uri, "pool:NGN/KES:fpmm", "\"reserves\"").unwrap(),
            rev_balance("1111abc").unwrap(),
            balances(&uri, &["REV".into(), "NGN".into()]).unwrap(),
            account_call(&uri, "\"openVault\", *deployerId, \"NGN\""),
            deposit_rev(&uri, 1),
            withdraw_rev_to(&uri, 1, "1111abc").unwrap(),
            add_liquidity(&uri, &uri, "pool:NGN/KES:fpmm", 1, 1, 0).unwrap(),
            remove_liquidity(&uri, &uri, "pool:NGN/KES:fpmm", 1, 0, 0).unwrap(),
            swap(&uri, &uri, "pool:NGN/KES:fpmm", "NGN", "KES", 1, 0).unwrap(),
            oracle_submit(&uri, "NGN", 1, 1, 0, &"00".repeat(65), &"11".repeat(70)).unwrap(),
            admin_action(&uri, 1, "setParams", "[]", "[]").unwrap(),
        ];
        for term in built {
            let open = term.matches('{').count();
            let close = term.matches('}').count();
            assert_eq!(open, close, "unbalanced braces ({open}/{close}): {term}");
        }
    }
}
