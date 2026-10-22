//! `rcash devnet demo`: the R2 acceptance journey.
//!
//! Every step is a real signed deploy against the configured devnet. There is no mock
//! data. The demo refreshes the oracle immediately before each freshness-gated step
//! because the devnet's 50-block freshness window is about half a minute.

use std::path::Path;

use rcash_chain::keystore::DevnetKeys;
use rcash_core::manifest::Manifest;
use rcash_sdk::Client;

/// One whole unit in base units.
const UNIT: i64 = 100_000_000;

/// Run the demo. Returns a description of the first failing step.
pub async fn run(
    node: &str,
    keys_path: &Path,
    manifest_path: &Path,
    json: bool,
) -> Result<(), String> {
    let manifest_text = std::fs::read_to_string(manifest_path)
        .map_err(|e| format!("{}: {e}", manifest_path.display()))?;
    let manifest = Manifest::from_json(&manifest_text).map_err(|e| e.to_string())?;
    let keys = DevnetKeys::load(keys_path).map_err(|e| e.to_string())?;

    let deployer_key = keys.key("deployer").map_err(|e| e.to_string())?;
    let recipient_key = keys
        .key("recipient")
        .or_else(|_| keys.key("deployer"))
        .map_err(|e| e.to_string())?;
    let reporters: Vec<Client> = (1..=2)
        .map(|i| {
            let key = keys.key(&format!("reporter{i}"))?;
            Ok(Client::new(node, key)?.with_manifest(manifest.clone()))
        })
        .collect::<Result<_, rcash_chain::ChainError>>()
        .map_err(|e| e.to_string())?;

    let deployer = Client::new(node, deployer_key)
        .map_err(|e| e.to_string())?
        .with_manifest(manifest.clone());
    let recipient = Client::new(node, recipient_key)
        .map_err(|e| e.to_string())?
        .with_manifest(manifest);

    let mut step = 0;
    let mut report = |name: &str| {
        step += 1;
        if !json {
            println!("[{step:02}] {name}");
        }
    };

    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;

    // The recipient pays phlo for its claim, so give it a little REV if needed.
    let recipient_addr = recipient.address().map_err(|e| e.to_string())?;
    if recipient
        .native_rev_balance(&recipient_addr)
        .await
        .map_err(|e| e.to_string())?
        < 10_000_000
    {
        let _ = recipient.node().faucet(&recipient_addr).await;
    }

    report("refresh the oracle (REV, NGN, KES)");
    refresh(
        &reporters,
        &[("REV", 5_000_000), ("NGN", 66_666), ("KES", 769_230)],
        tip,
    )
    .await?;

    report("fund the Account with 2 REV");
    deployer
        .deposit_rev(2 * UNIT)
        .await
        .map_err(|e| e.to_string())?;

    report("open the NGN vault, deposit 1 REV, borrow 1 NGN");
    deployer
        .vault_open("NGN")
        .await
        .map_err(|e| e.to_string())?;
    deployer
        .vault_deposit_collateral("NGN", UNIT)
        .await
        .map_err(|e| e.to_string())?;
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    refresh(&reporters, &[("REV", 5_000_000), ("NGN", 66_666)], tip).await?;
    deployer
        .vault_borrow("NGN", UNIT)
        .await
        .map_err(|e| e.to_string())?;

    report("open the KES vault, deposit 1 REV, borrow 1 KES");
    deployer
        .vault_open("KES")
        .await
        .map_err(|e| e.to_string())?;
    deployer
        .vault_deposit_collateral("KES", UNIT)
        .await
        .map_err(|e| e.to_string())?;
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    refresh(&reporters, &[("REV", 5_000_000), ("KES", 769_230)], tip).await?;
    deployer
        .vault_borrow("KES", UNIT)
        .await
        .map_err(|e| e.to_string())?;

    report("add 1 NGN of liquidity");
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    refresh(&reporters, &[("NGN", 66_666), ("KES", 769_230)], tip).await?;
    let quote = deployer
        .pool_quote_add_signed(UNIT)
        .await
        .map_err(|e| e.to_string())?;
    let shares = deployer
        .add_liquidity(UNIT, quote.quote, 0)
        .await
        .map_err(|e| e.to_string())?;

    report("remove 0.01 LP shares");
    deployer
        .remove_liquidity(1_000_000, 0, 0)
        .await
        .map_err(|e| e.to_string())?;

    report("convert 1 NGN to KES in one deploy");
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    refresh(&reporters, &[("NGN", 66_666), ("KES", 769_230)], tip).await?;
    let swap = deployer
        .convert("NGN", "KES", UNIT, 0)
        .await
        .map_err(|e| e.to_string())?;

    report("send 1 NGN to a claim link and claim it");
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    refresh(&reporters, &[("NGN", 66_666), ("KES", 769_230)], tip).await?;
    let secret = rcash_chain::claim::generate_secret_hex().map_err(|e| e.to_string())?;
    let hash = rcash_chain::claim::claim_hash(&secret).map_err(|e| e.to_string())?;
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    let transfer_id = deployer
        .send_transfer("NGN", "KES", UNIT, 0, &hash, tip + 60)
        .await
        .map_err(|e| e.to_string())?;
    let claimed = recipient
        .claim_transfer(transfer_id, "KES", &secret)
        .await
        .map_err(|e| e.to_string())?;

    report("send 1 NGN with a short expiry and refund it");
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    refresh(&reporters, &[("NGN", 66_666), ("KES", 769_230)], tip).await?;
    let secret = rcash_chain::claim::generate_secret_hex().map_err(|e| e.to_string())?;
    let hash = rcash_chain::claim::claim_hash(&secret).map_err(|e| e.to_string())?;
    let tip = deployer
        .node()
        .latest_block_number()
        .await
        .map_err(|e| e.to_string())?;
    let refund_id = deployer
        .send_transfer("NGN", "KES", UNIT, 0, &hash, tip + 2)
        .await
        .map_err(|e| e.to_string())?;
    // Two blocks plus a margin for finality.
    tokio::time::sleep(std::time::Duration::from_secs(8)).await;
    let refunded = deployer
        .refund_transfer(refund_id, "KES")
        .await
        .map_err(|e| e.to_string())?;

    report("read back balances");
    let balances = deployer
        .balances(&["REV", "NGN", "KES", "LP:NGN/KES:fpmm"])
        .await
        .map_err(|e| e.to_string())?;

    if json {
        println!(
            "{}",
            serde_json::json!({
                "status": "pass",
                "steps": step,
                "lpSharesAdded": shares,
                "convertedOut": swap.amount_out,
                "claimed": claimed.value(),
                "refunded": refunded.value(),
                "ownerId": balances.owner_id,
                "balances": balances
                    .amounts
                    .iter()
                    .map(|(asset, amount)| {
                        (asset.clone(), serde_json::Value::from(amount.to_decimal()))
                    })
                    .collect::<serde_json::Map<_, _>>(),
            })
        );
    } else {
        println!("\nR2 demo: PASS ({step} steps)");
        println!("  converted 1 NGN -> {} KES", swap.amount_out);
        println!("  claimed {}", claimed.to_decimal());
        println!("  refunded {}", refunded.to_decimal());
        for (asset, amount) in &balances.amounts {
            println!("  {asset}: {}", amount.to_decimal());
        }
    }
    Ok(())
}

async fn refresh(
    reporters: &[Client],
    currencies: &[(&str, i64)],
    height: i64,
) -> Result<(), String> {
    for (currency, price) in currencies {
        for (index, client) in reporters.iter().enumerate() {
            let key = client.key().ok_or("reporter client has no key")?;
            let (public, signature) =
                rcash_chain::claim::sign_oracle(key, currency, *price, height)
                    .map_err(|e| e.to_string())?;
            client
                .oracle_submit(currency, *price, height, index as i64, &public, &signature)
                .await
                .map_err(|e| e.to_string())?
                .into_result()
                .map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}
