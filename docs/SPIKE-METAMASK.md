# Spike: can MetaMask sign an RChain deploy?

**Status:** not run. **Current supported path:** MetaMask is a read-only identity; a locally
held encrypted secp256k1 key signs deploys.

## Why this is a spike and not a feature

`r-wallet`'s MetaMask wallet has an Ethereum address and a derived REV address, but no
public key and no private key. Every signing path in that wallet rejects it
(`src/utils/rnode.ts`: "`wallet` must be a signing account (not MetaMask)";
`src/modules/wallet/staking/Staking.tsx`: "MetaMask wallets have no pubKey here"). A REV
Account read or write requires `deployerId`, which requires a deploy, which requires a
signature. MetaMask alone therefore cannot operate an Account in v0.1.

## The route worth testing

The node supports a second deploy algorithm, `secp256k1:eth`:

1. Build the DeployData bytes with `rcash-chain` (the same bytes the normal path signs).
2. Compute `keccak256("\x19Ethereum Signed Message:\n" + decimal_length + bytes)`.
3. Call MetaMask `personal_sign` for the selected account over the hex-encoded bytes.
4. Convert MetaMask's 65-byte `r||s||v` to the node's raw 64-byte `R||S`, normalizing to
   low-S (`rchain_crypto::signatures::secp256k1_eth` has the helpers).
5. Recover the uncompressed public key from the hash and signature with `k256`.
6. Derive the REV address and compare it with the address derived from MetaMask's
   Ethereum account. They must match.
7. Submit with `sigAlgorithm: "secp256k1:eth"`, the recovered 65-byte public key as
   `deployer`, and the 64-byte `R||S` as `signature`.
8. Poll deploy status and finality.

`eth_sign` is not assumed: MetaMask often disables it and its prefix semantics differ.
WalletConnect is a transport, not a signer, and no common RChain wallet implements deploy
signing for it.

## Go / no-go

**GO** only if all of:

- `personal_sign` signs the exact bytes (verified by public-key recovery against the
  expected address);
- the node accepts and finalizes the deploy;
- it works in at least two browser/provider combinations.

**NO-GO** otherwise. Either way the local keystore remains the default signer, and
MetaMask signing — if it ever works — stays opt-in and experimental until audited.

## Record

No result yet. When run, record the provider and browser versions, the exact bytes hashed,
the recovered public key, the deploy id, the block hash, and the finality response here.
