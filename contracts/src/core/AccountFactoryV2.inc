// AccountFactory: ownerId -> {account: bundle, proof: unforgeable}.
// Captured: factoryState, revAddress, Directory, deployerIdOps.
// The proof is passed only into the Account at creation and is never returned by getOrCreate.

contract AccountFactory(@"getOrCreate", @pubKeyBytes, ret) = {
  new addrCh in {
    revAddress!("fromPublicKey", pubKeyBytes, *addrCh) |
    for (@ownerId <- addrCh) {
      for (@accounts <- factoryState) {
        match accounts.get(ownerId) {
          Nil => {
            new account, accountInternalPurse, accountLookupPurse, accountZone, accountVaultAuth,
                  accountEnsurePurse, accountTransferBookLegacy, accountAssetMeta,
                  accountControllerUri, accountBookById, accountBookFor,
                  proof, purseState, vaultState in {
              purseState!({}) |
              vaultState!({}) |
              // @@INLINE:core/AccountBodyV2.inc@@
              factoryState!(accounts.set(ownerId, {
                "account": bundle+{*account},
                "proof": *proof
              })) |
              ret!((true, bundle+{*account}, ownerId))
            }
          }
          entry => {
            factoryState!(accounts) |
            ret!((true, entry.get("account"), ownerId))
          }
        }
      }
    }
  }
} |

contract AccountFactory(@"verify", @ownerId, proof, ret) = {
  for (@accounts <<- factoryState) {
    match accounts.get(ownerId) {
      Nil => ret!((true, false))
      entry => ret!((true, entry.get("proof") == *proof))
    }
  }
} |

contract AccountFactory(@"accountOf", @ownerId, ret) = {
  for (@accounts <<- factoryState) {
    match accounts.get(ownerId) {
      Nil => ret!((false, "no account"))
      entry => ret!((true, entry.get("account")))
    }
  }
} |
