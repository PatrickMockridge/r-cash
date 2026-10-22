//! Rholang term templates for protocol calls.
//!
//! Every argument is rendered from a typed value in this crate; no caller-supplied text
//! reaches a term. Strings go through `rcash_core::rho::quote_str`, which refuses a
//! double quote (unrepresentable in Rholang).

use rcash_core::assets::RegistryUri;
use rcash_core::rho::{quote_str, quote_uri};
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
}
