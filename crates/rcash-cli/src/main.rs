//! `rcash` — the R-Cash command-line client.
//!
//! R1 surface: keys, node status, deploy/explore, status polling, the faucet, and typed
//! reads for accounts, the FX pool, the oracle, currency zones and transfers. The write
//! operations arrive in R2.

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
    /// Devnet keys file (plaintext; local tooling only).
    #[arg(long, global = true, default_value = ".devnet/keys.json")]
    keys: PathBuf,
    /// Named key to sign with. Defaults to the first key in the file.
    #[arg(long, global = true)]
    key: Option<String>,
    /// Deployment manifest (public component URIs; no keys).
    #[arg(long, global = true, default_value = "deployments/devnet.json")]
    manifest: PathBuf,
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
    /// Currency-zone reads.
    Zone {
        #[command(subcommand)]
        cmd: ZoneCmd,
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
}

#[derive(Subcommand, Debug)]
enum AccountCmd {
    /// Read several balances in one signed deploy.
    Balances {
        /// Comma-separated asset ids.
        #[arg(long, value_delimiter = ',')]
        assets: Vec<String>,
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
}

#[derive(Subcommand, Debug)]
enum ZoneCmd {
    /// One owner's vault.
    Vault {
        #[arg(long)]
        currency: String,
        #[arg(long)]
        owner: String,
    },
    /// All vaults in a currency zone.
    Vaults {
        #[arg(long)]
        currency: String,
    },
    /// Zone parameters.
    Params {
        #[arg(long)]
        currency: String,
    },
    /// Outstanding debt.
    Supply {
        #[arg(long)]
        currency: String,
    },
    /// `brand`, `issuer` or `currency`.
    Field {
        #[arg(long)]
        currency: String,
        #[arg(long)]
        field: String,
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
        Err(CliError::Chain(e)) => {
            eprintln!("rcash: {e}");
            ExitCode::from(3)
        }
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
            let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
            let status = node.status().await?;
            print_json_or(&cli.json, &status);
            Ok(ExitCode::SUCCESS)
        }
        Command::Deploy {
            file,
            term,
            no_wait,
        } => {
            let term = read_term(file, term)?;
            let key = load_key_from(&cli.keys, cli.key.as_deref())?;
            let client = Client::new(cli.node.clone(), key)?;
            if no_wait {
                let id = client.submit_term(&term).await?;
                if cli.json {
                    println!("{}", serde_json::json!({ "deployId": id }));
                } else {
                    println!("{id}");
                }
                return Ok(ExitCode::SUCCESS);
            }
            let outcome = client.deploy_term(&term).await?;
            if cli.json {
                println!(
                    "{}",
                    serde_json::json!({
                        "deployId": outcome.deploy_id,
                        "status": outcome.status.status_text(),
                        "blockHash": outcome.block_hash(),
                        "finalized": outcome.finalized,
                        "error": outcome.status.deploy_error(),
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
        Command::Explore { file, term } => {
            let term = read_term(file, term)?;
            let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
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
        Command::DeployStatus { id } => {
            let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
            let status = node.deploy_status(&id).await?;
            let value = serde_json::json!({
                "deployId": id,
                "status": status.status_text(),
                "blockHash": status.block().map(|b| b.block_hash.clone()),
                "error": status.deploy_error(),
            });
            print_json_or(&cli.json, &value);
            Ok(ExitCode::SUCCESS)
        }
        Command::Wait { id } => {
            let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
            let status = node.wait_processed(&id, Default::default()).await?;
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
        },
        Command::Pool { ref cmd } => {
            let client = reader_client(&cli)?;
            match cmd {
                PoolCmd::Quote { asset_in, amount } => {
                    let quote = client.pool_quote(asset_in, parse_amount(amount)?).await?;
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
                    let quote = client.pool_quote_add(parse_amount(base_amount)?).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "base": quote.base,
                            "quote": quote.quote,
                        }),
                    );
                }
                PoolCmd::Reserves => {
                    let reserves = client.pool_reserves().await?;
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
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Oracle { ref cmd } => {
            let client = reader_client(&cli)?;
            match cmd {
                OracleCmd::Get { currency } => {
                    let feed = client.oracle_price(currency).await?;
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
                    let rate = client.oracle_pair(base, quote).await?;
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
            }
            Ok(ExitCode::SUCCESS)
        }
        Command::Zone { ref cmd } => {
            let client = reader_client(&cli)?;
            match cmd {
                ZoneCmd::Vault { currency, owner } => {
                    let vault = client.zone_vault(currency, owner).await?;
                    print_json_or(
                        &cli.json,
                        &serde_json::json!({
                            "collateral": vault.collateral,
                            "debt": vault.debt,
                            "health": vault.healthy,
                            "liquidatable": vault.liquidatable,
                            "fresh": vault.fresh,
                            "rate": vault.rate,
                        }),
                    );
                }
                ZoneCmd::Vaults { currency } => {
                    let vaults = client.zone_vaults(currency).await?;
                    let value = serde_json::Value::Object(
                        vaults
                            .iter()
                            .map(|(owner, vault)| (owner.clone(), vault.to_json()))
                            .collect(),
                    );
                    print_json_or(&cli.json, &value);
                }
                ZoneCmd::Params { currency } => {
                    let params = client.zone_params(currency).await?;
                    let value = serde_json::Value::Object(
                        params
                            .iter()
                            .map(|(key, value)| (key.clone(), value.to_json()))
                            .collect(),
                    );
                    print_json_or(&cli.json, &value);
                }
                ZoneCmd::Supply { currency } => {
                    let supply = client.zone_supply(currency).await?;
                    print_json_or(&cli.json, &serde_json::json!({ "totalDebt": supply }));
                }
                ZoneCmd::Field { currency, field } => {
                    let value = client.zone_field(currency, field).await?;
                    print_json_or(&cli.json, &value.to_json());
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
                    let quote = client
                        .transfer_quote(source, dest, parse_amount(amount)?)
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
            }
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
        Command::Doctor { manifest } => {
            let node = rcash_chain::node::NodeClient::new(cli.node.clone())?;
            let status = node.status().await?;
            let key = load_key_from(&cli.keys, cli.key.as_deref())?;
            let address = key.rev_address()?;
            println!("node: {}", cli.node);
            println!("status: {}", status);
            println!("key: {address}");
            if let Some(path) = manifest {
                let text = std::fs::read_to_string(&path)
                    .map_err(|e| CliError::Usage(format!("{}: {e}", path.display())))?;
                let manifest = rcash_core::manifest::Manifest::from_json(&text)
                    .map_err(|e| CliError::Usage(e.to_string()))?;
                println!("manifest: directory {}", manifest.directory_uri);
            }
            Ok(ExitCode::SUCCESS)
        }
    }
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

fn reader_client(cli: &Cli) -> Result<Client> {
    Ok(Client::reader(cli.node.clone())?.with_manifest(load_manifest(&cli.manifest)?))
}

fn signing_client(cli: &Cli) -> Result<Client> {
    let key = load_key_from(&cli.keys, cli.key.as_deref())?;
    Ok(Client::new(cli.node.clone(), key)?.with_manifest(load_manifest(&cli.manifest)?))
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
