//! `rcash` — the R-Cash command-line client.
//!
//! R2 surface: keys, node status, deploy/explore, typed reads and writes for accounts,
//! the FX pool, the oracle and transfers.

use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use rcash_chain::keystore::DevnetKeys;
use rcash_chain::ChainError;
use rcash_sdk::Client;

#[derive(Parser, Debug)]
#[command(name = "rcash", version, about = "R-Cash devnet client", long_about = None)]
struct Cli {
    /// Node public HTTP API.
    #[arg(
        long,
        global = true,
        env = "RCASH_NODE",
        default_value = "http://localhost:40403"
    )]
    node: String,
    /// Additional known nodes for the endpoint pool, comma-separated or repeated. The
    /// hostlist is still discovered in the background and augments this list.
    #[arg(long, global = true, env = "RCASH_NODES", value_delimiter = ',')]
    nodes: Vec<String>,
    /// Disable hostlist discovery; the pool then uses --node/--nodes only.
    #[arg(long, global = true, env = "RCASH_NO_HOSTLIST")]
    no_hostlist: bool,
    /// Shard id carried by every signed deploy.
    #[arg(long, global = true, env = "RCASH_SHARD", default_value = "/root")]
    shard_id: String,
    /// Phlo limit for signed deploys.
    #[arg(
        long,
        global = true,
        env = "RCASH_PHLO_LIMIT",
        default_value_t = 1_000_000
    )]
    phlo_limit: i64,
    /// Phlo price for signed deploys.
    #[arg(long, global = true, env = "RCASH_PHLO_PRICE", default_value_t = 1)]
    phlo_price: i64,
    /// Devnet keys file (plaintext; local tooling only).
    #[arg(long, global = true, default_value = ".devnet/keys.json")]
    keys: PathBuf,
    /// Named key to sign with. Defaults to the first key in the file.
    #[arg(long, global = true)]
    key: Option<String>,
    /// Deployment manifest (public component URIs; no keys).
    #[arg(long, global = true, default_value = "deployments/devnet.json")]
    manifest: PathBuf,
    /// v0.4 deployment manifest.
    #[arg(long, global = true, default_value = "deployments/devnet-v4.json")]
    v4_manifest: PathBuf,
    /// Machine-readable output.
    #[arg(long, global = true)]
    json: bool,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Generate a devnet keys file.
    Keygen {
        #[arg(long)]
        out: Option<PathBuf>,
        /// Comma-separated key names.
        #[arg(long, default_value = "deployer")]
        names: String,
        /// Replace an existing file.
        #[arg(long)]
        force: bool,
        /// Fund each new address from the devnet faucet.
        #[arg(long)]
        faucet: bool,
    },
    /// Print the selected key's REV address and public key.
    Address,
    /// Node status.
    Status,
    /// Sign and submit a term.
    Deploy {
        /// A file containing the term.
        file: Option<PathBuf>,
        /// A term literal (used when no file is given).
        #[arg(long)]
        term: Option<String>,
        /// Submit without waiting for processing and finality.
        #[arg(long)]
        no_wait: bool,
        /// Operation id for an idempotent, cached deploy.
        #[arg(long)]
        op: Option<String>,
        /// Directory holding write-ahead signed deploys.
        #[arg(long, default_value = ".rcash-ops")]
        op_cache: PathBuf,
    },
    /// Run a term without signing or charging phlo.
    Explore {
        file: Option<PathBuf>,
        #[arg(long)]
        term: Option<String>,
    },
    /// Show a deploy's execution status.
    DeployStatus { id: String },
    /// Wait for a deploy to be processed by the node.
    Wait { id: String },
    /// Request devnet REV for an address.
    Faucet { address: String },
    /// Check the node, key and manifest a client would use.
    Doctor {
        #[arg(long)]
        manifest: Option<PathBuf>,
    },
    /// Write a deterministic signing fixture for the TypeScript parity test.
    ParityFixture { out: PathBuf },
    /// v0.4 reads and writes: accounts, transfers, stablecoins and markets.
    V4 {
        #[command(subcommand)]
        cmd: V4Cmd,
    },
    /// Account reads.
    Account {
        #[command(subcommand)]
        cmd: AccountCmd,
    },
    /// FX pool reads.
    Pool {
        #[command(subcommand)]
        cmd: PoolCmd,
    },
    /// Oracle reads.
    Oracle {
        #[command(subcommand)]
        cmd: OracleCmd,
    },
    /// Transfer-book reads.
    Transfer {
        #[command(subcommand)]
        cmd: TransferCmd,
    },
    /// Native REV balance of an address.
    Balance {
        #[arg(long)]
        address: String,
    },
    /// Convert one local currency to another in one atomic deploy.
    Convert {
        #[arg(long)]
        from: String,
        #[arg(long)]
        to: String,
        #[arg(long)]
        amount: String,
        #[arg(long, default_value = "0")]
        min_out: String,
    },
    /// End-to-end devnet journeys.
    Devnet {
        #[command(subcommand)]
        cmd: DevnetCmd,
    },
}

#[derive(Subcommand, Debug)]
enum DevnetCmd {
    /// Fund the account, send a claimable REV transfer to self and claim it.
    Demo {
        #[arg(long, default_value = "0.01")]
        amount: String,
        #[arg(long, default_value = "720")]
        blocks: i64,
    },
}

#[derive(Subcommand, Debug)]
enum AccountCmd {
    /// Read several balances in one signed deploy.
    Balances {
        /// Comma-separated asset ids.
        #[arg(long, value_delimiter = ',')]
        assets: Vec<String>,
    },
    /// Fund the Account with REV from the native vault.
    Deposit {
        #[arg(long)]
        amount: String,
    },
    /// Withdraw REV to a native REV address.
    WithdrawRev {
        #[arg(long)]
        amount: String,
        #[arg(long)]
        to: String,
    },
}

#[derive(Subcommand, Debug)]
enum PoolCmd {
    /// Quote a swap.
    Quote {
        #[arg(long)]
        asset_in: String,
        #[arg(long)]
        amount: String,
    },
    /// Quote the quote-side amount matching a base deposit.
    QuoteAdd {
        #[arg(long)]
        base_amount: String,
    },
    /// Reserves, total shares, rate and freshness.
    Reserves,
    /// Pool parameters.
    Params,
    /// The pool's pair.
    Pair,
    /// The LP token's brand and issuer.
    LpAsset,
    /// Add liquidity from the Account.
    Add {
        #[arg(long)]
        base: String,
        #[arg(long)]
        quote: String,
        #[arg(long, default_value = "0")]
        min_shares: String,
    },
    /// Remove liquidity into the Account.
    Remove {
        #[arg(long)]
        shares: String,
        #[arg(long, default_value = "0")]
        min_base: String,
        #[arg(long, default_value = "0")]
        min_quote: String,
    },
    /// Swap from the Account.
    Swap {
        #[arg(long)]
        asset_in: String,
        #[arg(long)]
        asset_out: String,
        #[arg(long)]
        amount: String,
        #[arg(long, default_value = "0")]
        min_out: String,
    },
}

#[derive(Subcommand, Debug)]
enum OracleCmd {
    /// One currency's feed.
    Get {
        #[arg(long)]
        currency: String,
    },
    /// A cross rate from two feeds.
    Pair {
        #[arg(long)]
        base: String,
        #[arg(long)]
        quote: String,
    },
    /// The reporter public keys.
    Reporters,
    /// Sign and submit a reporter price with the selected key.
    Submit {
        #[arg(long)]
        currency: String,
        #[arg(long)]
        price: String,
        /// Block height the price was observed at. Defaults to the tip.
        #[arg(long)]
        height: Option<i64>,
        /// Reporter index in the allowlist.
        #[arg(long, default_value = "0")]
        index: i64,
    },
}

#[derive(Subcommand, Debug)]
enum TransferCmd {
    /// A transfer's public record.
    Info {
        #[arg(long)]
        id: i64,
    },
    /// The next transfer id.
    NextId,
    /// Quote a transfer.
    Quote {
        #[arg(long)]
        source: String,
        #[arg(long)]
        dest: String,
        #[arg(long)]
        amount: String,
    },
    /// Send a claimable transfer.
    Send {
        #[arg(long)]
        source: String,
        #[arg(long)]
        dest: String,
        #[arg(long)]
        amount: String,
        #[arg(long, default_value = "0")]
        min_dest: String,
        /// Claim secret hex. Generated when omitted.
        #[arg(long)]
        secret: Option<String>,
        /// Blocks from the tip until the sender may refund.
        #[arg(long, default_value = "720")]
        expiry_blocks: i64,
    },
    /// Claim a transfer with its secret.
    Claim {
        #[arg(long)]
        id: i64,
        #[arg(long)]
        dest: String,
        #[arg(long)]
        secret: String,
    },
    /// Refund an expired transfer.
    Refund {
        #[arg(long)]
        id: i64,
        #[arg(long)]
        dest: String,
    },
}

/// The refusal class a shell script can branch on, if this is a designed refusal.
fn refusal_code(error: &ChainError) -> Option<(&'static str, Option<u64>)> {
    match error {
        ChainError::RateLimited { retry_after, .. } => Some(("429", *retry_after)),
        ChainError::Unavailable { retry_after, .. } => Some(("503", *retry_after)),
        ChainError::AdmissionRefused { .. } => Some(("admission", None)),
        ChainError::Duplicate { .. } => Some(("duplicate", None)),
        ChainError::TermTooLarge { .. } => Some(("term-too-large", None)),
        _ => None,
    }
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(e) => {
            eprintln!("rcash: {e}");
            return ExitCode::from(3);
        }
    };
    match runtime.block_on(run(cli)) {
        Ok(code) => code,
        Err(CliError::Usage(message)) => {
            eprintln!("rcash: {message}");
            ExitCode::from(2)
        }
        Err(CliError::Chain(e)) => match refusal_code(&e) {
            Some((code, retry_after)) => {
                eprintln!(
                    "REFUSED code={code} retry_after={} detail={e}",
                    retry_after.unwrap_or(0)
                );
                ExitCode::from(4)
            }
            None => {
                eprintln!("rcash: {e}");
                ExitCode::from(3)
            }
        },
    }
}

#[derive(Debug, thiserror::Error)]
enum CliError {
    #[error("{0}")]
    Usage(String),
    #[error(transparent)]
    Chain(#[from] ChainError),
}

type Result<T> = std::result::Result<T, CliError>;

async fn run(cli: Cli) -> Result<ExitCode> {
    match cli.command {
        Command::Keygen {
            out,
            names,
            force,
            faucet,
        } => {
            let out = out.unwrap_or_else(|| cli.keys.clone());
            if out.exists() && !force {
                return Err(CliError::Usage(format!(
                    "{} exists; pass --force to replace it",
                    out.display()
                )));
            }
            let mut keys = DevnetKeys::default();
            for name in names.split(',').map(str::trim).filter(|n| !n.is_empty()) {
                keys.insert_generated(name)?;
            }
            if faucet {
                let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
                for entry in keys.keys.values_mut() {
                    match node.faucet(&entry.address).await {
                        Ok(_) => entry.funded = true,
                        Err(e) => eprintln!("faucet: {}: {e}", entry.name),
                    }
                }
            }
            keys.save(&out)?;
            for entry in keys.keys.values() {
                println!(
                    "{}  {}  {}{}",
                    entry.name,
                    entry.address,
                    entry.public,
                    if entry.funded { "  funded" } else { "" }
                );
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Address => {
            let key = load_key(&cli)?;
            let address = key.rev_address()?;
            if cli.json {
                println!(
                    "{}",
                    serde_json::json!({
                        "address": address,
                        "public": key.public_hex(),
                    })
                );
            } else {
                println!("{address}");
                println!("{}", key.public_hex());
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Status => {
            let node = node_client(&cli)?;
            let status = node.seed_status().await?;
            print_json_or(&cli.json, &status);
            Ok(ExitCode::SUCCESS)
        }
        Command::Deploy {
            ref file,
            ref term,
            no_wait,
            ref op,
            ref op_cache,
        } => {
            let term = read_term(file.clone(), term.clone())?;
            let key = load_key_from(&cli.keys, cli.key.as_deref())?;
            let client = with_network(Client::with_node(node_client(&cli)?, Some(key)), &cli);
            if no_wait && op.is_none() {
                let id = client.submit_term(&term).await?;
                if cli.json {
                    println!("{}", serde_json::json!({ "deployId": id }));
                } else {
                    println!("{id}");
                }
                return Ok(ExitCode::SUCCESS);
            }
            let outcome = match op {
                Some(op) => client.deploy_term_cached(&term, op, op_cache).await?,
                None => client.deploy_term(&term).await?,
            };
            if cli.json {
                println!(
                    "{}",
                    serde_json::json!({
                        "deployId": outcome.deploy_id,
                        "status": outcome.status.status_text(),
                        "blockHash": outcome.block_hash(),
                        "finalized": outcome.finalized,
                        "error": outcome.status.deploy_error(),
                        "result": outcome.status.deploy_result(),
                    })
                );
            } else {
                println!(
                    "deploy {}: {}",
                    outcome.deploy_id,
                    outcome.status.status_text()
                );
                if let Some(hash) = outcome.block_hash() {
                    println!("block {hash} final={}", outcome.finalized);
                }
                if let Some(error) = outcome.status.deploy_error() {
                    println!("error: {error}");
                }
            }
            if !outcome.is_success() {
                return Ok(ExitCode::from(1));
            }
            if !outcome.finalized {
                return Ok(ExitCode::from(3));
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Explore { ref file, ref term } => {
            let term = read_term(file.clone(), term.clone())?;
            let node = node_client(&cli)?;
            let response = node.explore(&term).await?;
            let value = serde_json::json!({
                "expr": response.expr,
                "block": {
                    "blockHash": response.block.block_hash,
                    "blockNumber": response.block.block_number,
                },
                "replySource": response.reply_source,
            });
            print_json_or(&cli.json, &value);
            Ok(ExitCode::SUCCESS)
        }
        Command::DeployStatus { ref id } => {
            let node = node_client(&cli)?;
            let status = node.deploy_status(id).await?;
            let value = serde_json::json!({
                "deployId": id,
                "status": status.status_text(),
                "blockHash": status.block().map(|b| b.block_hash.clone()),
                "error": status.deploy_error(),
            });
            print_json_or(&cli.json, &value);
            Ok(ExitCode::SUCCESS)
        }
        Command::Wait { ref id } => {
            let node = node_client(&cli)?;
            let status = node.wait_processed(id, Default::default()).await?;
            let value = serde_json::json!({
                "deployId": id,
                "status": status.status_text(),
                "blockHash": status.block().map(|b| b.block_hash.clone()),
                "error": status.deploy_error(),
            });
            print_json_or(&cli.json, &value);
            Ok(if status.is_success() {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            })
        }
        Command::Faucet { address } => {
            let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
            let response = node.faucet(&address).await?;
            print_json_or(&cli.json, &response);
            Ok(ExitCode::SUCCESS)
        }
        Command::ParityFixture { out } => {
            use rcash_chain::deploy::DeployOptions;
            // A fixed, throwaway key: the fixture is a test vector, not a wallet.
            let secret = "01".repeat(32);
            let key = rcash_chain::KeyPair::from_secret_hex(&secret)?;
            let data = DeployOptions::new("Nil")
                .timestamp(1_700_000_000_000)
                .phlo(1_000_000, 1)
                .valid_after_block_number(12_345)
                .shard_id("/root")
                .build()?;
            let signed = key.sign_deploy(data)?;
            let encoded = signed.encoded_hex();
            let fixture = serde_json::json!({
                "secret": secret,
                "data": {
                    "term": signed.data.term,
                    "timestamp": signed.data.timestamp,
                    "phloPrice": signed.data.phlo_price,
                    "phloLimit": signed.data.phlo_limit,
                    "validAfterBlockNumber": signed.data.valid_after_block_number,
                    "shardId": signed.data.shard_id,
                },
                "encoded": encoded,
                "deployer": signed.deployer_hex,
                "signature": signed.signature_hex,
                "deployId": signed.deploy_id,
                "address": key.rev_address()?,
            });
            std::fs::write(&out, serde_json::to_string_pretty(&fixture).unwrap())
                .map_err(|e| CliError::Usage(format!("{}: {e}", out.display())))?;
            println!("{}", out.display());
            Ok(ExitCode::SUCCESS)
        }
        Command::V4 { ref cmd } => {
            match cmd {
                V4Cmd::Currency { code } => {
                    let currency = v4_reader(&cli)?.v4_currency(code).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "code": currency.code,
                            "kind": currency.kind,
                            "stablecoinUri": currency.stablecoin_uri,
                            "vaultUri": currency.vault_uri,
                            "paramsHash": currency.params_hash,
                            "status": currency.status,
                            "assetUri": currency.asset_uri,
                            "decimals": currency.decimals,
                            "chain": currency.chain,
                            "custodian": currency.custodian,
                        }),
                    );
                }
                V4Cmd::Market { base, quote } => {
                    let market = v4_reader(&cli)?.v4_market(base, quote).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "base": base,
                            "quote": quote,
                            "marketId": market.as_ref().map(|m| &m.market_id),
                            "version": market.as_ref().map(|m| m.version),
                            "status": market.as_ref().map(|m| &m.status),
                            "termsHash": market.as_ref().map(|m| &m.terms_hash),
                        }),
                    );
                }
                V4Cmd::Active { market } => {
                    let active = v4_reader(&cli)?.v4_is_active(market).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "market": market, "active": active,
                        }),
                    );
                }
                V4Cmd::Activate { market } => {
                    let status = v4_signing_client(&cli)?.v4_activate(market).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "market": market, "status": status,
                        }),
                    );
                }
                V4Cmd::Slot { market } => {
                    let slot = v4_reader(&cli)?.v4_slot(market).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "market": market, "pool": slot.pool_uri, "lock": slot.lock_uri,
                        }),
                    );
                }
                V4Cmd::LockInfo { lock } => {
                    let l = v4_reader(&cli)?.v4_lock_info(lock).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "funded": l.funded, "released": l.released,
                            "cancelled": l.cancelled, "untilHeight": l.until_height,
                            "shares": l.shares,
                        }),
                    );
                }
                V4Cmd::Quote {
                    pool,
                    direction,
                    amount,
                } => {
                    let q = v4_signing_client(&cli)?
                        .v4_quote(pool, direction, parse_amount(amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "pool": pool, "amountOut": q.amount_out,
                            "fee": q.fee, "rate": q.rate,
                        }),
                    );
                }
                V4Cmd::Reserves { pool } => {
                    let r = v4_reader(&cli)?.v4_reserves(pool).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "base": r.base, "quote": r.quote,
                            "totalShares": r.total_shares, "seeded": r.seeded,
                        }),
                    );
                }
                V4Cmd::Supply { stablecoin } => {
                    let supply = v4_reader(&cli)?.v4_supply(stablecoin).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "stablecoin": stablecoin, "supply": supply,
                        }),
                    );
                }
                V4Cmd::TransferInfo { transfer } => {
                    let t = v4_reader(&cli)?.v4_transfer(transfer).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "sender": t.sender, "asset": t.asset, "amount": t.amount,
                            "expiry": t.expiry, "status": t.status,
                        }),
                    );
                }
                V4Cmd::Balance { asset } => {
                    let balance = v4_signing_client(&cli)?.v4_balance(asset).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "asset": asset, "baseUnits": balance,
                        }),
                    );
                }
                V4Cmd::FundRev { amount } => {
                    let balance = v4_signing_client(&cli)?
                        .v4_fund_rev(parse_amount(amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "asset": "REV", "baseUnits": balance,
                        }),
                    );
                }
                V4Cmd::Send {
                    to_pub,
                    asset,
                    amount,
                    secret_hash,
                    expiry,
                    memo,
                    op_id,
                    stipend,
                } => {
                    let sent = v4_signing_client(&cli)?
                        .v4_send_transfer(
                            to_pub,
                            asset,
                            parse_amount(amount)?,
                            secret_hash,
                            *expiry,
                            memo,
                            op_id,
                            parse_amount(stipend)?,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "id": sent.id, "transfer": sent.uri,
                        }),
                    );
                }
                V4Cmd::Claim { transfer, secret } => {
                    let balance = v4_signing_client(&cli)?
                        .v4_claim_transfer(transfer, secret)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "transfer": transfer, "baseUnits": balance,
                        }),
                    );
                }
                V4Cmd::Refund { transfer } => {
                    let balance = v4_signing_client(&cli)?
                        .v4_refund_transfer(transfer)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "transfer": transfer, "baseUnits": balance,
                        }),
                    );
                }
                V4Cmd::Swap {
                    pool,
                    direction,
                    asset_in,
                    asset_out,
                    amount,
                    min_out,
                } => {
                    let out = v4_signing_client(&cli)?
                        .v4_swap(
                            pool,
                            direction,
                            asset_in,
                            asset_out,
                            parse_amount(amount)?,
                            parse_amount(min_out)?,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "pool": pool, "amountOut": out,
                        }),
                    );
                }
                V4Cmd::AddLiquidity {
                    pool,
                    lock,
                    base,
                    quote,
                    base_amount,
                    quote_amount,
                    until,
                    min_shares,
                } => {
                    let shares = v4_signing_client(&cli)?
                        .v4_add_liquidity(
                            pool,
                            lock,
                            base,
                            quote,
                            parse_amount(base_amount)?,
                            parse_amount(quote_amount)?,
                            *until,
                            parse_amount(min_shares)?,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "pool": pool, "shares": shares,
                        }),
                    );
                }
                V4Cmd::ReleaseLp {
                    lock,
                    pool,
                    base,
                    quote,
                    min_base,
                    min_quote,
                } => {
                    let shares = v4_signing_client(&cli)?
                        .v4_release_lp(
                            lock,
                            pool,
                            base,
                            quote,
                            parse_amount(min_base)?,
                            parse_amount(min_quote)?,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "lock": lock, "shares": shares,
                        }),
                    );
                }
                V4Cmd::VaultMint {
                    vault,
                    currency,
                    collateral,
                    mint,
                } => {
                    let debt = v4_signing_client(&cli)?
                        .v4_vault_mint(
                            vault,
                            currency,
                            parse_amount(collateral)?,
                            parse_amount(mint)?,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "vault": vault, "debt": debt,
                        }),
                    );
                }
                V4Cmd::VaultRepay {
                    vault,
                    currency,
                    amount,
                } => {
                    let debt = v4_signing_client(&cli)?
                        .v4_vault_repay(vault, currency, parse_amount(amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "vault": vault, "debt": debt,
                        }),
                    );
                }
                V4Cmd::VaultWithdraw { vault, amount } => {
                    let withdrawn = v4_signing_client(&cli)?
                        .v4_vault_withdraw(vault, parse_amount(amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "vault": vault, "baseUnits": withdrawn,
                        }),
                    );
                }
                V4Cmd::Currencies => {
                    let list = v4_reader(&cli)?.v4_currencies().await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!(list
                            .iter()
                            .map(|c| serde_json::json!({
                                "code": c.code, "kind": c.kind,
                                "stablecoinUri": c.stablecoin_uri,
                                "vaultUri": c.vault_uri, "savingsUri": c.savings_uri,
                                "psmUri": c.psm_uri, "bufferUri": c.buffer_uri,
                                "status": c.status, "assetUri": c.asset_uri,
                                "decimals": c.decimals, "chain": c.chain,
                                "custodian": c.custodian,
                            }))
                            .collect::<Vec<_>>()),
                    );
                }
                V4Cmd::Markets => {
                    let list = v4_reader(&cli)?.v4_markets().await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!(list
                            .iter()
                            .map(|m| serde_json::json!({
                                "marketId": m.market_id, "slug": m.slug,
                                "base": m.base, "quote": m.quote,
                                "version": m.version, "status": m.status,
                            }))
                            .collect::<Vec<_>>()),
                    );
                }
                V4Cmd::Terms { hash } => {
                    let terms = v4_reader(&cli)?.v4_terms(hash).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "values": terms.values,
                            "terms": terms.terms.keys().collect::<Vec<_>>(),
                        }),
                    );
                }
                V4Cmd::Transfers => {
                    let map = v4_signing_client(&cli)?.v4_transfers().await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "ops": map.keys().collect::<Vec<_>>(),
                        }),
                    );
                }
                V4Cmd::BufferInfo { buffer } => {
                    let info = v4_reader(&cli)?.v4_buffer_info(buffer).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "surplus": info.surplus, "sin": info.sin,
                            "savingsShareBps": info.savings_share_bps, "rev": info.rev,
                        }),
                    );
                }
                V4Cmd::RiskParams { params } => {
                    let info = v4_reader(&cli)?.v4_risk_params(params).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "paramsHash": info.params_hash, "currentHash": info.current_hash,
                            "rev": info.rev, "params": info.params.keys().collect::<Vec<_>>(),
                        }),
                    );
                }
                V4Cmd::SavingsInfo { savings } => {
                    let info = v4_reader(&cli)?.v4_savings_info(savings).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "totalShares": info.total_shares, "totalAssets": info.total_assets,
                            "shareValueE8": info.share_value_e8, "rev": info.rev,
                        }),
                    );
                }
                V4Cmd::SavingsPosition { savings } => {
                    let pos = v4_signing_client(&cli)?
                        .v4_savings_position(savings)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"shares": pos.shares}));
                }
                V4Cmd::SavingsDeposit {
                    savings,
                    currency,
                    amount,
                } => {
                    let shares = v4_signing_client(&cli)?
                        .v4_savings_deposit(savings, currency, parse_amount(amount)?)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"shares": shares}));
                }
                V4Cmd::SavingsWithdraw {
                    savings,
                    currency,
                    shares,
                } => {
                    let amount = v4_signing_client(&cli)?
                        .v4_savings_withdraw(savings, currency, parse_amount(shares)?)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"baseUnits": amount}));
                }
                V4Cmd::PsmInfo { psm } => {
                    let info = v4_reader(&cli)?.v4_psm_info(psm).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "stableDebt": info.stable_debt, "feeBps": info.fee_bps,
                            "ceiling": info.ceiling, "revBalance": info.rev_balance,
                            "rev": info.rev,
                        }),
                    );
                }
                V4Cmd::PsmBuy {
                    psm,
                    currency,
                    rev_amount,
                    min_stable,
                } => {
                    let out = v4_signing_client(&cli)?
                        .v4_psm_buy(
                            psm,
                            currency,
                            parse_amount(rev_amount)?,
                            parse_amount(min_stable)?,
                        )
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"stableOut": out}));
                }
                V4Cmd::PsmSell {
                    psm,
                    currency,
                    amount,
                    min_rev,
                } => {
                    let out = v4_signing_client(&cli)?
                        .v4_psm_sell(psm, currency, parse_amount(amount)?, parse_amount(min_rev)?)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"revOut": out}));
                }
                V4Cmd::VaultOpen { vault } => {
                    v4_signing_client(&cli)?.v4_vault_open(vault).await?;
                    print_json_or(&cli.json, &serde_json::json!({"vault": vault, "ok": true}));
                }
                V4Cmd::VaultDeposit { vault, amount } => {
                    let collateral = v4_signing_client(&cli)?
                        .v4_vault_deposit(vault, parse_amount(amount)?)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"collateral": collateral}));
                }
                V4Cmd::VaultInfo { vault } => {
                    let v = v4_signing_client(&cli)?.v4_vault(vault).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "collateral": v.collateral, "debt": v.debt,
                            "accruedInterest": v.accrued_interest, "health": v.health,
                            "rate": v.rate, "fresh": v.fresh,
                        }),
                    );
                }
                V4Cmd::Totals { vault } => {
                    let t = v4_reader(&cli)?.v4_totals(vault).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "totalDebt": t.total_debt, "badDebt": t.bad_debt,
                            "sin": t.sin, "psmDebt": t.psm_debt, "paused": t.paused,
                        }),
                    );
                }
                V4Cmd::VaultLiquidate {
                    liquidation,
                    currency,
                    owner,
                    amount,
                    min_collateral,
                } => {
                    let seized = v4_signing_client(&cli)?
                        .v4_vault_liquidate(
                            liquidation,
                            currency,
                            owner,
                            parse_amount(amount)?,
                            parse_amount(min_collateral)?,
                        )
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"seized": seized}));
                }
                V4Cmd::Pending { domain, nonce } => {
                    let pending = v4_reader(&cli)?.v4_pending(domain, *nonce).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!(pending.map(|p| serde_json::json!({
                            "action": p.action, "argsHash": p.args_hash,
                            "readyAt": p.ready_at,
                        }))),
                    );
                }
                V4Cmd::MarketStatus {
                    market,
                    status,
                    nonce,
                    sigs,
                } => {
                    v4_signing_client(&cli)?
                        .v4_set_market_status(market, status, *nonce, sigs)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"ok": true}));
                }
                V4Cmd::PauseCurrency {
                    code,
                    paused,
                    nonce,
                    sigs,
                } => {
                    v4_signing_client(&cli)?
                        .v4_pause_currency(code, *paused, *nonce, sigs)
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({"ok": true}));
                }
                V4Cmd::CreateMarket { terms } => {
                    let text = std::fs::read_to_string(terms)
                        .map_err(|e| CliError::Usage(format!("{}: {e}", terms.display())))?;
                    let terms: rcash_core::market::MarketTerms =
                        serde_json::from_str(&text).map_err(|e| CliError::Usage(e.to_string()))?;
                    let created = v4_signing_client(&cli)?.v4_create_market(&terms).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "marketId": created.market_id, "pool": created.pool_uri,
                            "lock": created.lock_uri, "termsHash": created.terms_hash,
                        }),
                    );
                }
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Devnet { ref cmd } => match cmd {
            DevnetCmd::Demo { amount, blocks } => {
                let client = v4_signing_client(&cli)?;
                let amount = parse_amount(amount)?;
                client.v4_fund_rev(amount).await?;
                let pubkey = client
                    .key()
                    .ok_or_else(|| CliError::Usage("a signing key is required".into()))?
                    .public_hex();
                let secret = rcash_chain::claim::generate_secret_hex()?;
                let hash = rcash_chain::claim::claim_hash(&secret)?;
                let tip = client.height().await?;
                let sent = client
                    .v4_send_transfer(
                        &pubkey,
                        "REV",
                        amount,
                        &hash,
                        tip + blocks,
                        "devnet demo",
                        "",
                        0,
                    )
                    .await?;
                let claimed = client.v4_claim_transfer(&sent.uri, &secret).await?;
                print_json_or(
                    &cli.json,
                    &serde_json::json!({
                        "transfer": sent.uri, "id": sent.id,
                        "claimedBaseUnits": claimed,
                    }),
                );
                Ok(ExitCode::SUCCESS)
            }
        },
        Command::Account { ref cmd } => match cmd {
            AccountCmd::Balances { assets } => {
                if assets.is_empty() {
                    return Err(CliError::Usage("--assets is required".into()));
                }
                let refs: Vec<&str> = assets.iter().map(String::as_str).collect();
                let client = signing_client(&cli)?;
                let balances = client.balances(&refs).await?;
                let amounts: serde_json::Map<String, serde_json::Value> = balances
                    .amounts
                    .iter()
                    .map(|(asset, amount)| {
                        (
                            asset.clone(),
                            serde_json::json!({
                                "decimal": amount.to_decimal(),
                                "baseUnits": amount.value(),
                            }),
                        )
                    })
                    .collect();
                print_json_or(
                    &cli.json,
                    &serde_json::json!({
                        "ownerId": balances.owner_id,
                        "amounts": amounts,
                    }),
                );
                Ok(ExitCode::SUCCESS)
            }
            AccountCmd::Deposit { amount } => {
                let client = signing_client(&cli)?;
                let balance = client.deposit_rev(parse_amount(amount)?).await?;
                print_json_or(
                    &cli.json,
                    &serde_json::json!({
                        "balance": balance.to_decimal(),
                        "baseUnits": balance.value(),
                    }),
                );
                Ok(ExitCode::SUCCESS)
            }
            AccountCmd::WithdrawRev { amount, to } => {
                let client = signing_client(&cli)?;
                client
                    .withdraw_rev_to(parse_amount(amount)?, to)
                    .await?
                    .into_result()?;
                print_json_or(
                    &cli.json,
                    &serde_json::json!({ "withdrawn": amount, "to": to }),
                );
                Ok(ExitCode::SUCCESS)
            }
        },
        Command::Pool { ref cmd } => {
            let client = reader_client(&cli)?;
            match cmd {
                PoolCmd::Quote { asset_in, amount } => {
                    let client = signing_client(&cli)?;
                    let quote = client
                        .pool_quote_signed(asset_in, parse_amount(amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "amountOut": quote.amount_out,
                            "fee": quote.fee,
                            "rate": quote.rate,
                            "maxIn": quote.max_in,
                        }),
                    );
                }
                PoolCmd::QuoteAdd { base_amount } => {
                    let client = signing_client(&cli)?;
                    let quote = client
                        .pool_quote_add_signed(parse_amount(base_amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "base": quote.base,
                            "quote": quote.quote,
                        }),
                    );
                }
                PoolCmd::Reserves => {
                    let client = signing_client(&cli)?;
                    let reserves = client.pool_reserves_signed().await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "reserveBase": reserves.base,
                            "reserveQuote": reserves.quote,
                            "totalShares": reserves.total_shares,
                            "rate": reserves.rate,
                            "fresh": reserves.fresh,
                            "paused": reserves.paused,
                        }),
                    );
                }
                PoolCmd::Params => {
                    let params = client.pool_params().await?;
                    let value = serde_json::Value::Object(
                        params
                            .iter()
                            .map(|(key, value)| (key.clone(), value.to_json()))
                            .collect(),
                    );
                    print_json_or(&cli.json, &value);
                }
                PoolCmd::Pair => {
                    let (base, quote) = client.pool_pair().await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({ "base": base, "quote": quote }),
                    );
                }
                PoolCmd::LpAsset => {
                    let values = client.pool_lp_asset().await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::Value::Array(values.iter().map(|v| v.to_json()).collect()),
                    );
                }
                PoolCmd::Add {
                    base,
                    quote,
                    min_shares,
                } => {
                    let client = signing_client(&cli)?;
                    let shares = client
                        .add_liquidity(
                            parse_amount(base)?,
                            parse_amount(quote)?,
                            parse_amount(min_shares)?,
                        )
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({ "shares": shares }));
                }
                PoolCmd::Remove {
                    shares,
                    min_base,
                    min_quote,
                } => {
                    let client = signing_client(&cli)?;
                    let burned = client
                        .remove_liquidity(
                            parse_amount(shares)?,
                            parse_amount(min_base)?,
                            parse_amount(min_quote)?,
                        )
                        .await?;
                    print_json_or(&cli.json, &serde_json::json!({ "shares": burned }));
                }
                PoolCmd::Swap {
                    asset_in,
                    asset_out,
                    amount,
                    min_out,
                } => {
                    let client = signing_client(&cli)?;
                    let result = client
                        .swap(
                            asset_in,
                            asset_out,
                            parse_amount(amount)?,
                            parse_amount(min_out)?,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "amountOut": result.amount_out,
                            "fee": result.fee,
                        }),
                    );
                }
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Oracle { ref cmd } => {
            let client = reader_client(&cli)?;
            match cmd {
                OracleCmd::Get { currency } => {
                    let client = signing_client(&cli)?;
                    let feed = client.oracle_price_signed(currency).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "price": feed.price,
                            "height": feed.height,
                            "fresh": feed.fresh,
                            "reason": feed.reason,
                        }),
                    );
                }
                OracleCmd::Pair { base, quote } => {
                    let client = signing_client(&cli)?;
                    let rate = client.oracle_pair_signed(base, quote).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "rate": rate.rate,
                            "fresh": rate.fresh,
                            "reason": rate.reason,
                        }),
                    );
                }
                OracleCmd::Reporters => {
                    let reporters = client.oracle_reporters().await?;
                    print_json_or(&cli.json, &serde_json::json!(reporters));
                }
                OracleCmd::Submit {
                    currency,
                    price,
                    height,
                    index,
                } => {
                    let client = signing_client(&cli)?;
                    let height = match *height {
                        Some(height) => height,
                        None => client.node().latest_block_number().await?,
                    };
                    let price = parse_amount(price)?;
                    let (public, signature) = rcash_chain::claim::sign_oracle(
                        client.key().expect("signing client"),
                        currency,
                        price,
                        height,
                    )?;
                    client
                        .oracle_submit(currency, price, height, *index, &public, &signature)
                        .await?
                        .into_result()?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "currency": currency,
                            "price": price,
                            "height": height,
                            "index": index,
                        }),
                    );
                }
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Transfer { ref cmd } => {
            let client = reader_client(&cli)?;
            match cmd {
                TransferCmd::Info { id } => {
                    let info = client.transfer_info(*id).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "sender": info.sender,
                            "source": info.source,
                            "dest": info.dest,
                            "amount": info.amount,
                            "claimHash": info.claim_hash_hex,
                            "expiry": info.expiry,
                            "status": info.status,
                        }),
                    );
                }
                TransferCmd::NextId => {
                    let next = client.transfer_next_id().await?;
                    print_json_or(&cli.json, &serde_json::json!({ "nextId": next }));
                }
                TransferCmd::Quote {
                    source,
                    dest,
                    amount,
                } => {
                    let client = signing_client(&cli)?;
                    let quote = client
                        .transfer_quote_signed(source, dest, parse_amount(amount)?)
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "amountOut": quote.amount_out,
                            "fee": quote.fee,
                            "rate": quote.rate,
                            "maxIn": quote.max_in,
                        }),
                    );
                }
                TransferCmd::Send {
                    source,
                    dest,
                    amount,
                    min_dest,
                    secret,
                    expiry_blocks,
                } => {
                    let client = signing_client(&cli)?;
                    let secret_hex = match secret {
                        Some(secret) => secret.clone(),
                        None => rcash_chain::claim::generate_secret_hex()?,
                    };
                    let claim_hash = rcash_chain::claim::claim_hash(&secret_hex)?;
                    let tip = client.node().latest_block_number().await?;
                    let expiry = tip + expiry_blocks;
                    let transfer_id = client
                        .send_transfer(
                            source,
                            dest,
                            parse_amount(amount)?,
                            parse_amount(min_dest)?,
                            &claim_hash,
                            expiry,
                        )
                        .await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "transferId": transfer_id,
                            "claimSecret": secret_hex,
                            "claimHash": claim_hash,
                            "expiryHeight": expiry,
                            "claimFragment": format!("#/claim/{transfer_id}/{secret_hex}"),
                        }),
                    );
                }
                TransferCmd::Claim { id, dest, secret } => {
                    let client = signing_client(&cli)?;
                    let amount = client.claim_transfer(*id, dest, secret).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "transferId": id,
                            "claimed": amount.to_decimal(),
                            "baseUnits": amount.value(),
                        }),
                    );
                }
                TransferCmd::Refund { id, dest } => {
                    let client = signing_client(&cli)?;
                    let amount = client.refund_transfer(*id, dest).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "transferId": id,
                            "refunded": amount.to_decimal(),
                            "baseUnits": amount.value(),
                        }),
                    );
                }
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Convert {
            ref from,
            ref to,
            ref amount,
            ref min_out,
        } => {
            let client = signing_client(&cli)?;
            let result = client
                .convert(from, to, parse_amount(amount)?, parse_amount(min_out)?)
                .await?;
            print_json_or(
                &cli.json,
                &serde_json::json!({
                    "from": from,
                    "to": to,
                    "amountOut": result.amount_out,
                    "fee": result.fee,
                }),
            );
            Ok(ExitCode::SUCCESS)
        }
        Command::Balance { ref address } => {
            let client = reader_client(&cli)?;
            let balance = client.native_rev_balance(address).await?;
            print_json_or(
                &cli.json,
                &serde_json::json!({
                    "baseUnits": balance,
                    "rev": rcash_core::Amount::raw(balance).to_decimal(),
                }),
            );
            Ok(ExitCode::SUCCESS)
        }
        Command::Doctor { ref manifest } => {
            let node = node_client(&cli)?;
            let status = node.seed_status().await?;
            let key = load_key_from(&cli.keys, cli.key.as_deref())?;
            let address = key.rev_address()?;
            let discovery =
                if node.discovery_mode() == rcash_chain::node::pool::DiscoveryMode::Disabled {
                    Err(ChainError::NoEligibleNode {
                        reason: "hostlist discovery disabled by --no-hostlist or --nodes".into(),
                    })
                } else {
                    node.discover().await
                };
            let report = discovery.as_ref().ok().cloned();
            let error = discovery.as_ref().err().map(ToString::to_string);
            if cli.json {
                let value = serde_json::json!({
                    "node": cli.node,
                    "status": status,
                    "key": address,
                    "discovery": report,
                    "error": error,
                    "nodes": node.nodes(),
                });
                println!("{value}");
            } else {
                println!("node: {}", cli.node);
                println!("status: {status}");
                println!("key: {address}");
                match (&report, &error) {
                    (Some(report), _) => {
                        println!(
                            "hostlist: published (network {}, shard {})",
                            report.network_id.as_deref().unwrap_or("-"),
                            report.primary_shard.as_deref().unwrap_or("-")
                        );
                        let accepting = report
                            .endpoints
                            .iter()
                            .filter(|endpoint| endpoint.accepts_deploys)
                            .count();
                        println!(
                            "endpoints: {} verified, {accepting} accepting",
                            report.endpoints.len()
                        );
                        for endpoint in &report.endpoints {
                            println!(
                                "  {}  shard={} tip={} minPhloPrice={} accepting={} source={:?}",
                                endpoint.base,
                                endpoint.shard_id.as_deref().unwrap_or("-"),
                                endpoint.latest_block_number,
                                endpoint.min_phlo_price,
                                endpoint.accepts_deploys,
                                endpoint.source
                            );
                        }
                    }
                    (None, Some(error))
                        if matches!(
                            discovery.as_ref().err(),
                            Some(ChainError::HostlistUnsupported)
                        ) =>
                    {
                        println!("hostlist: not published (GET /api/v1/nodes returned 404)");
                        println!("error: {error}");
                    }
                    (None, Some(error)) => println!("hostlist: unavailable ({error})"),
                    (None, None) => {}
                }
            }
            if let Some(path) = manifest {
                let text = std::fs::read_to_string(path)
                    .map_err(|e| CliError::Usage(format!("{}: {e}", path.display())))?;
                let manifest = rcash_core::manifest::Manifest::from_json(&text)
                    .map_err(|e| CliError::Usage(e.to_string()))?;
                if !cli.json {
                    println!("manifest: directory {}", manifest.directory_uri);
                }
            }
            Ok(ExitCode::SUCCESS)
        }
    }
}

#[derive(Subcommand, Debug)]
enum V4Cmd {
    /// A listed currency's stablecoin and vault URIs.
    Currency { code: String },
    /// The market record for a direct pair.
    Market { base: String, quote: String },
    /// Whether a market is active.
    Active { market: String },
    /// Activate a seeded market.
    Activate { market: String },
    /// A market's pool and lock URIs.
    Slot { market: String },
    /// The seed lock's state.
    LockInfo { lock: String },
    /// A pool quote.
    Quote {
        pool: String,
        direction: String,
        amount: String,
    },
    /// A pool's reserves.
    Reserves { pool: String },
    /// A stablecoin's total supply.
    Supply { stablecoin: String },
    /// A transfer's public record.
    TransferInfo { transfer: String },
    /// The caller's balance of one asset.
    Balance { asset: String },
    /// Fund the caller's account with REV.
    FundRev { amount: String },
    /// Send a claimable transfer to a recipient public key.
    Send {
        to_pub: String,
        asset: String,
        amount: String,
        secret_hash: String,
        expiry: i64,
        #[arg(long, default_value = "")]
        memo: String,
        #[arg(long, default_value = "")]
        op_id: String,
        #[arg(long, default_value = "0")]
        stipend: String,
    },
    /// Claim a transfer with its secret.
    Claim { transfer: String, secret: String },
    /// Refund an expired transfer.
    Refund { transfer: String },
    /// Swap through a pool and deposit the output.
    Swap {
        pool: String,
        direction: String,
        asset_in: String,
        asset_out: String,
        amount: String,
        #[arg(long, default_value = "0")]
        min_out: String,
    },
    /// Add both sides of a market and lock the seed LP.
    AddLiquidity {
        pool: String,
        lock: String,
        base: String,
        quote: String,
        base_amount: String,
        quote_amount: String,
        until: i64,
        /// Minimum LP shares (use the quote-derived floor, never zero in production).
        #[arg(long)]
        min_shares: String,
    },
    /// Release the seed LP after the lock height and remove it.
    ReleaseLp {
        lock: String,
        pool: String,
        base: String,
        quote: String,
        #[arg(long)]
        min_base: String,
        #[arg(long)]
        min_quote: String,
    },
    /// Mint a stablecoin against REV into the account.
    VaultMint {
        vault: String,
        currency: String,
        collateral: String,
        mint: String,
    },
    /// Repay vault debt.
    VaultRepay {
        vault: String,
        currency: String,
        amount: String,
    },
    /// Withdraw REV collateral into the account.
    VaultWithdraw { vault: String, amount: String },
    /// Every listed currency.
    Currencies,
    /// Every staged or listed market.
    Markets,
    /// A market's canonical terms.
    Terms { hash: String },
    /// The caller's transfer op ledger.
    Transfers,
    /// Surplus-buffer state.
    BufferInfo { buffer: String },
    /// Risk parameters and hashes.
    RiskParams { params: String },
    /// Savings-pool state.
    SavingsInfo { savings: String },
    /// The caller's savings position.
    SavingsPosition { savings: String },
    /// Deposit stablecoin into savings.
    SavingsDeposit {
        savings: String,
        currency: String,
        amount: String,
    },
    /// Withdraw savings shares.
    SavingsWithdraw {
        savings: String,
        currency: String,
        shares: String,
    },
    /// PSM state.
    PsmInfo { psm: String },
    /// Mint stablecoin at par through the PSM.
    PsmBuy {
        psm: String,
        currency: String,
        rev_amount: String,
        min_stable: String,
    },
    /// Redeem stablecoin at par through the PSM.
    PsmSell {
        psm: String,
        currency: String,
        amount: String,
        min_rev: String,
    },
    /// Open or reuse the caller's vault.
    VaultOpen { vault: String },
    /// Deposit REV collateral.
    VaultDeposit { vault: String, amount: String },
    /// The caller's vault position.
    VaultInfo { vault: String },
    /// The issuer's accounting totals.
    Totals { vault: String },
    /// Liquidate an unhealthy vault.
    VaultLiquidate {
        liquidation: String,
        currency: String,
        owner: String,
        amount: String,
        min_collateral: String,
    },
    /// A scheduled governor action.
    Pending { domain: String, nonce: i64 },
    /// Change a market's status with governor signatures.
    MarketStatus {
        market: String,
        status: String,
        nonce: i64,
        sigs: Vec<String>,
    },
    /// Pause or resume a currency with governor signatures.
    PauseCurrency {
        code: String,
        paused: bool,
        nonce: i64,
        sigs: Vec<String>,
    },
    /// Create a market from a JSON terms file.
    CreateMarket { terms: std::path::PathBuf },
}

fn load_key(cli: &Cli) -> Result<rcash_chain::KeyPair> {
    load_key_from(&cli.keys, cli.key.as_deref())
}

fn load_key_from(path: &std::path::Path, name: Option<&str>) -> Result<rcash_chain::KeyPair> {
    let keys = DevnetKeys::load(path)?;
    match name {
        Some(name) => Ok(keys.key(name)?),
        None => Ok(keys.first_key()?),
    }
}

fn parse_amount(value: &str) -> Result<i64> {
    Ok(rcash_core::Amount::parse(value)
        .map_err(|e| CliError::Usage(e.to_string()))?
        .value())
}

fn load_manifest(path: &std::path::Path) -> Result<rcash_core::manifest::Manifest> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| CliError::Usage(format!("{}: {e}", path.display())))?;
    rcash_core::manifest::Manifest::from_json(&text).map_err(|e| CliError::Usage(e.to_string()))
}

fn load_v4_manifest(path: &std::path::Path) -> Result<rcash_core::manifest::V4Manifest> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| CliError::Usage(format!("{}: {e}", path.display())))?;
    rcash_core::manifest::V4Manifest::from_json(&text).map_err(|e| CliError::Usage(e.to_string()))
}

fn with_network(client: Client, cli: &Cli) -> Client {
    client
        .with_shard(cli.shard_id.clone())
        .with_phlo(cli.phlo_limit, cli.phlo_price)
}

/// Build the pooled node client from the global flags.
///
/// Discovery is on by default and runs in the background; `--nodes` adds known endpoints
/// to it. `--no-hostlist` is the escape hatch that leaves only --node/--nodes.
fn node_client(cli: &Cli) -> Result<rcash_chain::node::NodeClient> {
    use rcash_chain::node::pool::{DiscoveryMode, PoolOptions};
    let discovery = if cli.no_hostlist {
        DiscoveryMode::Disabled
    } else {
        DiscoveryMode::Enabled
    };
    let options = PoolOptions {
        discovery,
        shard_id: cli.shard_id.clone(),
        explicit_nodes: cli.nodes.clone(),
        ..PoolOptions::default()
    };
    Ok(rcash_chain::node::NodeClient::new_with_options(
        cli.node.clone(),
        options,
    )?)
}

fn v4_reader(cli: &Cli) -> Result<Client> {
    Ok(
        with_network(Client::with_node(node_client(cli)?, None), cli)
            .with_v4_manifest(load_v4_manifest(&cli.v4_manifest)?),
    )
}

fn v4_signing_client(cli: &Cli) -> Result<Client> {
    let key = load_key_from(&cli.keys, cli.key.as_deref())?;
    Ok(
        with_network(Client::with_node(node_client(cli)?, Some(key)), cli)
            .with_v4_manifest(load_v4_manifest(&cli.v4_manifest)?),
    )
}

fn reader_client(cli: &Cli) -> Result<Client> {
    Ok(
        with_network(Client::with_node(node_client(cli)?, None), cli)
            .with_manifest(load_manifest(&cli.manifest)?),
    )
}

fn signing_client(cli: &Cli) -> Result<Client> {
    let key = load_key_from(&cli.keys, cli.key.as_deref())?;
    Ok(
        with_network(Client::with_node(node_client(cli)?, Some(key)), cli)
            .with_manifest(load_manifest(&cli.manifest)?),
    )
}

fn read_term(file: Option<PathBuf>, term: Option<String>) -> Result<String> {
    match (file, term) {
        (Some(path), None) => std::fs::read_to_string(&path)
            .map_err(|e| CliError::Usage(format!("{}: {e}", path.display()))),
        (None, Some(term)) => Ok(term),
        (Some(_), Some(_)) => Err(CliError::Usage(
            "pass either a file or --term, not both".into(),
        )),
        (None, None) => Err(CliError::Usage("pass a term file or --term <TERM>".into())),
    }
}

fn print_json_or(json: &bool, value: &serde_json::Value) {
    if *json {
        println!("{value}");
    } else {
        println!(
            "{}",
            serde_json::to_string_pretty(value).unwrap_or_default()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::Parser;
    use rcash_chain::node::pool::DiscoveryMode;

    fn parse(args: &[&str]) -> Cli {
        Cli::try_parse_from(args).expect("cli parses")
    }

    #[test]
    fn the_endpoint_pool_flags_choose_discovery() {
        let default = parse(&["rcash", "status"]);
        assert_eq!(
            node_client(&default).unwrap().discovery_mode(),
            DiscoveryMode::Enabled
        );

        let explicit = parse(&[
            "rcash",
            "--nodes",
            "http://a:40403,http://b:40403",
            "status",
        ]);
        assert_eq!(explicit.nodes.len(), 2);
        assert_eq!(
            node_client(&explicit).unwrap().discovery_mode(),
            DiscoveryMode::Enabled
        );

        let off = parse(&["rcash", "--no-hostlist", "status"]);
        assert_eq!(
            node_client(&off).unwrap().discovery_mode(),
            DiscoveryMode::Disabled
        );

        let both = parse(&[
            "rcash",
            "--nodes",
            "http://a:40403",
            "--no-hostlist",
            "status",
        ]);
        assert_eq!(
            node_client(&both).unwrap().discovery_mode(),
            DiscoveryMode::Disabled
        );
    }
}
