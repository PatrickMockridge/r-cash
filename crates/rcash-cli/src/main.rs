//! `rcash` — the R-Cash command-line client.
//!
//! R0a surface: keys, node status, deploy, explore, status polling and the faucet. The
//! protocol operation groups (account, vault, pool, transfer, oracle, admin) are added in
//! R1/R2.

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
