// AccountBody: the per-key non-custodial Account. Inlined inside AccountFactory's
// `new account, accountInternalPurse, accountLookupPurse, proof, purseState, vaultState in { ... }`.
//
// Captured names: pubKeyBytes, ownerId, proof, purseState, vaultState, Directory, deployerIdOps.
// Authority: every owner op presents the deploy's own *deployerId; this body makes one read-only
// `pubKeyBytes` call and compares it with the owner key. It never stores, emits or spends with it.
//
// Concurrency rule: never hold a consumed state cell across an external await. Reads use `<<-`
// peeks; the only state mutations happen after the purse/zone call has returned.

// Lazily create a purse for an asset and return it on ret. Does not touch state.
// Phase 1 implements the REV kind; stable/LP controllers arrive with their contracts.
contract accountInternalPurse(@assetId, @meta, ret) = {
  if (meta.get("kind") == "rev") {
    new rl(`rho:registry:lookup`), ertpCh, issuerCh, purseCh in {
      rl!(`rho:rchain:ertp`, *ertpCh) |
      for (@(_, ERTP) <- ertpCh) {
        @ERTP!("getRevIssuer", *issuerCh) |
        for (@(revBrand, issuer) <- issuerCh) {
          @issuer!("makeEmptyPurse", *purseCh) |
          for (@(true, purse) <- purseCh) {
            ret!((true, purse, revBrand))
          }
        }
      }
    }
  } else {
    if (meta.get("kind") == "stable") {
      new uriCh, rl(`rho:registry:lookup`), capCh, issuerCh, brandCh, purseCh in {
        Directory!("get", meta.get("controllerKey"), *uriCh) |
        for (@u <- uriCh) {
          match u {
            (true, uri) => {
              rl!(uri, *capCh) |
              for (zone <- capCh) {
                zone!("issuer", *issuerCh) |
                zone!("brand", *brandCh) |
                for (@(true, issuer) <- issuerCh; @(true, brand) <- brandCh) {
                  @issuer!("makeEmptyPurse", *purseCh) |
                  for (@(true, purse) <- purseCh) { ret!((true, purse, brand)) }
                }
              }
            }
            _ => ret!((false, "no controller"))
          }
        }
      }
    } else {
      if (meta.get("kind") == "lp") {
        new uriCh, rl(`rho:registry:lookup`), capCh, assetCh, poolCh, purseCh in {
          Directory!("get", "component:pools", *uriCh) |
          for (@u <- uriCh) {
            match u {
              (true, uri) => {
                rl!(uri, *capCh) |
                for (components <- capCh) {
                  components!("get", meta.get("controllerKey"), *poolCh) |
                  for (@(true, pool) <- poolCh) {
                    @pool!("lpAsset", *assetCh) |
                    for (@(true, lpBrand, lpIssuer) <- assetCh) {
                      @lpIssuer!("makeEmptyPurse", *purseCh) |
                      for (@(true, purse) <- purseCh) { ret!((true, purse, lpBrand)) }
                    }
                  }
                }
              }
              _ => ret!((false, "no controller"))
            }
          }
        }
      } else {
        ret!((false, "unsupported asset kind"))
      }
    }
  }
} |

// Return the stored purse for an asset, or Nil. Peek only.
contract accountLookupPurse(@assetId, ret) = {
  for (@purses <<- purseState) {
    match purses.get(assetId) {
      Nil => ret!(Nil)
      entry => {
        match entry.get("purse") {
          p => {
            match entry.get("brand") {
              brand => ret!((p, brand))
            }
          }
        }
      }
    }
  }
} |

contract accountZone(@currency, ret) = {
  new uriCh in {
    Directory!("get", "component:zone:" ++ currency, *uriCh) |
    for (@r <- uriCh) {
      match r {
        (true, uri) => {
          new rl(`rho:registry:lookup`), capCh in {
            rl!(uri, *capCh) |
            for (zone <- capCh) { ret!((true, *zone)) }
          }
        }
        _ => ret!((false, "no zone"))
      }
    }
  }
} |

contract accountVaultAuth(@currency, ret) = {
  for (@vs <<- vaultState) {
    match vs.get(currency) {
      Nil => ret!(Nil)
      auth => ret!(auth)
    }
  }
} |

// Ensure this Account has a purse for an asset, creating it if absent. The state mutation
// happens only after the purse exists.
contract accountEnsurePurse(@assetId, ret) = {
  new lookupCh, infoCh in {
    accountLookupPurse!(assetId, *lookupCh) |
    Directory!("asset", assetId, *infoCh) |
    for (@found <- lookupCh; @info <- infoCh) {
      match found {
        Nil => {
          match info {
            (true, meta) => {
              new createdCh in {
                accountInternalPurse!(assetId, meta, *createdCh) |
                for (@created <- createdCh) {
                  match created {
                    (true, purse, brand) => {
                      for (@ps <- purseState) {
                        match ps.get(assetId) {
                          Nil => {
                            purseState!(ps.set(assetId, {"purse": purse, "brand": brand})) |
                            ret!((true, purse, brand))
                          }
                          entry => {
                            purseState!(ps) |
                            match entry.get("purse") {
                              p => {
                                match entry.get("brand") {
                                  b => ret!((true, p, b))
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                    _ => ret!(created)
                  }
                }
              }
            }
            _ => ret!((false, "unknown asset"))
          }
        }
        (p, brand) => ret!((true, p, brand))
      }
    }
  }
} |

contract account(@"deposit", @assetId, payment, ret) = {
  new infoCh, lookupCh in {
    Directory!("asset", assetId, *infoCh) |
    accountLookupPurse!(assetId, *lookupCh) |
    for (@info <- infoCh; @found <- lookupCh) {
      match info {
        (true, meta) => {
          match found {
            Nil => {
              new newPurseCh in {
                accountInternalPurse!(assetId, meta, *newPurseCh) |
                for (@created <- newPurseCh) {
                  match created {
                    (true, purse, brand) => {
                      for (@purses <- purseState) {
                        match purses.get(assetId) {
                          Nil => {
                            purseState!(purses.set(assetId, {"purse": purse, "brand": brand})) |
                            @purse!("deposit", *payment, *ret)
                          }
                          entry => {
                            purseState!(purses) |
                            match entry.get("purse") {
                              p => @p!("deposit", *payment, *ret)
                            }
                          }
                        }
                      }
                    }
                    _ => ret!(created)
                  }
                }
              }
            }
            (p, brand) => {
              @p!("deposit", *payment, *ret)
            }
          }
        }
        _ => ret!((false, "unknown asset"))
      }
    }
  }
} |

contract account(@"withdraw", deployerId, @assetId, @amount, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new lookupCh in {
          accountLookupPurse!(assetId, *lookupCh) |
          for (@found <- lookupCh) {
            match found {
              Nil => ret!((false, "no purse"))
              (p, brand) => @p!("withdraw", (brand, amount), *ret)
            }
          }
        }
      } else {
        ret!((false, "not owner"))
      }
    }
  }
} |

contract account(@"balance", deployerId, @assetId, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new lookupCh in {
          accountLookupPurse!(assetId, *lookupCh) |
          for (@found <- lookupCh) {
            match found {
              Nil => ret!((false, "no purse"))
              (p, brand) => @p!("getCurrentAmount", *ret)
            }
          }
        }
      } else {
        ret!((false, "not owner"))
      }
    }
  }
} |

contract account(@"depositFacet", @assetId, ret) = {
  new infoCh, lookupCh in {
    Directory!("asset", assetId, *infoCh) |
    accountLookupPurse!(assetId, *lookupCh) |
    for (@info <- infoCh; @found <- lookupCh) {
      match info {
        (true, meta) => {
          match found {
            Nil => {
              new newPurseCh in {
                accountInternalPurse!(assetId, meta, *newPurseCh) |
                for (@created <- newPurseCh) {
                  match created {
                    (true, purse, brand) => {
                      for (@purses <- purseState) {
                        match purses.get(assetId) {
                          Nil => {
                            purseState!(purses.set(assetId, {"purse": purse, "brand": brand})) |
                            @purse!("getDepositFacet", *ret)
                          }
                          entry => {
                            purseState!(purses) |
                            match entry.get("purse") {
                              p => @p!("getDepositFacet", *ret)
                            }
                          }
                        }
                      }
                    }
                    _ => ret!(created)
                  }
                }
              }
            }
            (p, brand) => @p!("getDepositFacet", *ret)
          }
        }
        _ => ret!((false, "unknown asset"))
      }
    }
  }
} |


// ---- Transfer product ops ----------------------------------------------------------------
contract accountTransferBook(ret) = {
  new uriCh, rl(`rho:registry:lookup`), capCh, bookCh in {
    Directory!("get", "component:pools", *uriCh) |
    for (@u <- uriCh) {
      match u {
        (true, uri) => {
          rl!(uri, *capCh) |
          for (components <- capCh) {
            components!("get", "transfer:NGN/KES", *bookCh) |
            for (@(true, book) <- bookCh) { ret!((true, book)) }
          }
        }
        _ => ret!((false, "no book"))
      }
    }
  }
} |

contract account(@"sendTransfer", deployerId, @sourceAsset, @destAsset, @sourceAmount,
                @minDest, @claimHash, @expiry, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new purseCh in {
          accountEnsurePurse!(sourceAsset, *purseCh) |
          for (@pc <- purseCh) {
            match pc {
              (true, purse, brand) => {
                new wdCh in {
                  @purse!("withdraw", (brand, sourceAmount), *wdCh) |
                  for (@wp <- wdCh) {
                    match wp {
                      (true, payment) => {
                        new bookCh in {
                          accountTransferBook!(*bookCh) |
                          for (@b <- bookCh) {
                            match b {
                              (true, book) => {
                                @book!("send", sourceAsset, destAsset, payment, minDest,
                                       claimHash, expiry, ownerId, *proof, *ret)
                              }
                              _ => ret!((false, "no book"))
                            }
                          }
                        }
                      }
                      _ => ret!(wp)
                    }
                  }
                }
              }
              _ => ret!(pc)
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"claimTransfer", @transferId, @destAsset, @secret, ret) = {
  new purseCh in {
    accountEnsurePurse!(destAsset, *purseCh) |
    for (@pc <- purseCh) {
      match pc {
        (true, purse, brand) => {
          new bookCh in {
            accountTransferBook!(*bookCh) |
            for (@b <- bookCh) {
              match b {
                (true, book) => {
                  new cCh in {
                    @book!("claim", transferId, secret, *cCh) |
                    for (@c <- cCh) {
                      match c {
                        (true, amount, payment) => {
                          new claimDepCh in {
                            @purse!("deposit", payment, *claimDepCh) |
                            for (@d <- claimDepCh) { ret!((true, amount)) }
                          }
                        }
                        _ => ret!(c)
                      }
                    }
                  }
                }
                _ => ret!((false, "no book"))
              }
            }
          }
        }
        _ => ret!(pc)
      }
    }
  }
} |

contract account(@"refundTransfer", deployerId, @transferId, @destAsset, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new purseCh in {
          accountEnsurePurse!(destAsset, *purseCh) |
          for (@pc <- purseCh) {
            match pc {
              (true, purse, brand) => {
                new bookCh in {
                  accountTransferBook!(*bookCh) |
                  for (@b <- bookCh) {
                    match b {
                      (true, book) => {
                        new cCh in {
                          @book!("refund", transferId, ownerId, *proof, *cCh) |
                          for (@c <- cCh) {
                            match c {
                              (true, amount, payment) => {
                                new refundDepCh in {
                                  @purse!("deposit", payment, *refundDepCh) |
                                  for (@d <- refundDepCh) { ret!((true, amount)) }
                                }
                              }
                              _ => ret!(c)
                            }
                          }
                        }
                      }
                      _ => ret!((false, "no book"))
                    }
                  }
                }
              }
              _ => ret!(pc)
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

// ---- Vault operations (phase 3) ---------------------------------------------------------
// Every owner op authenticates the deploy's own *deployerId against pubKeyBytes, then uses the
// vaultAuth stored by openVault. The zone never sees the deployerId.

contract account(@"openVault", deployerId, @currency, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new zoneCh in {
          accountZone!(currency, *zoneCh) |
          for (@z <- zoneCh) {
            match z {
              (true, zone) => {
                new vCh in {
                  @zone!("open", ownerId, *proof, *vCh) |
                  for (@r <- vCh) {
                    match r {
                      (true, auth) => {
                        for (@vs <- vaultState) {
                          vaultState!(vs.set(currency, auth)) |
                          ret!((true, ownerId))
                        }
                      }
                      _ => ret!(r)
                    }
                  }
                }
              }
              _ => ret!((false, "no zone"))
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"depositCollateral", deployerId, @currency, @amount, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new authCh in {
          accountVaultAuth!(currency, *authCh) |
          for (@a <- authCh) {
            match a {
              Nil => ret!((false, "open a vault first"))
              auth => {
                new purseCh in {
                  accountEnsurePurse!("REV", *purseCh) |
                  for (@pc <- purseCh) {
                    match pc {
                      (true, purse, revBrand) => {
                        new payCh in {
                          @purse!("withdraw", (revBrand, amount), *payCh) |
                          for (@wp <- payCh) {
                            match wp {
                              (true, payment) => {
                                new zoneCh in {
                                  accountZone!(currency, *zoneCh) |
                                  for (@z <- zoneCh) {
                                    match z {
                                      (true, zone) => {
                                        @zone!("depositCollateral", ownerId, auth, payment, *ret)
                                      }
                                      _ => ret!((false, "no zone"))
                                    }
                                  }
                                }
                              }
                              _ => ret!(wp)
                            }
                          }
                        }
                      }
                      _ => ret!(pc)
                    }
                  }
                }
              }
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"withdrawCollateral", deployerId, @currency, @amount, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new authCh in {
          accountVaultAuth!(currency, *authCh) |
          for (@a <- authCh) {
            match a {
              Nil => ret!((false, "open a vault first"))
              auth => {
                new zoneCh in {
                  accountZone!(currency, *zoneCh) |
                  for (@z <- zoneCh) {
                    match z {
                      (true, zone) => {
                        new payCh in {
                          @zone!("withdrawCollateral", ownerId, auth, amount, *payCh) |
                          for (@wp <- payCh) {
                            match wp {
                              (true, payment) => {
                                new purseCh in {
                                  accountEnsurePurse!("REV", *purseCh) |
                                  for (@pc <- purseCh) {
                                    match pc {
                                      (true, purse, revBrand) => {
                                        new depCh in {
                                        @purse!("deposit", payment, *depCh) |
                                        for (@d <- depCh) { ret!((true, amount)) }
                                        }
                                      }
                                      _ => ret!(pc)
                                    }
                                  }
                                }
                              }
                              _ => ret!(wp)
                            }
                          }
                        }
                      }
                      _ => ret!((false, "no zone"))
                    }
                  }
                }
              }
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"borrow", deployerId, @currency, @amount, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new authCh in {
          accountVaultAuth!(currency, *authCh) |
          for (@a <- authCh) {
            match a {
              Nil => ret!((false, "open a vault first"))
              auth => {
                new purseCh in {
                  accountEnsurePurse!(currency, *purseCh) |
                  for (@pc <- purseCh) {
                    match pc {
                      (true, purse, brand) => {
                        new facetCh in {
                          @purse!("getDepositFacet", *facetCh) |
                          for (@f <- facetCh) {
                            match f {
                              (true, facet) => {
                                new zoneCh in {
                                  accountZone!(currency, *zoneCh) |
                                  for (@z <- zoneCh) {
                                    match z {
                                      (true, zone) => {
                                        @zone!("borrow", ownerId, auth, amount, facet, *ret)
                                      }
                                      _ => ret!((false, "no zone"))
                                    }
                                  }
                                }
                              }
                              _ => ret!(f)
                            }
                          }
                        }
                      }
                      _ => ret!(pc)
                    }
                  }
                }
              }
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"repay", deployerId, @currency, @amount, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new authCh in {
          accountVaultAuth!(currency, *authCh) |
          for (@a <- authCh) {
            match a {
              Nil => ret!((false, "open a vault first"))
              auth => {
                new purseCh in {
                  accountEnsurePurse!(currency, *purseCh) |
                  for (@pc <- purseCh) {
                    match pc {
                      (true, purse, brand) => {
                        new payCh in {
                          @purse!("withdraw", (brand, amount), *payCh) |
                          for (@wp <- payCh) {
                            match wp {
                              (true, payment) => {
                                new zoneCh in {
                                  accountZone!(currency, *zoneCh) |
                                  for (@z <- zoneCh) {
                                    match z {
                                      (true, zone) => {
                                        @zone!("repay", ownerId, auth, payment, *ret)
                                      }
                                      _ => ret!((false, "no zone"))
                                    }
                                  }
                                }
                              }
                              _ => ret!(wp)
                            }
                          }
                        }
                      }
                      _ => ret!(pc)
                    }
                  }
                }
              }
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"liquidate", deployerId, @currency, @victimOwnerId, @amount, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new purseCh in {
          accountEnsurePurse!(currency, *purseCh) |
          for (@pc <- purseCh) {
            match pc {
              (true, purse, brand) => {
                new payCh in {
                  @purse!("withdraw", (brand, amount), *payCh) |
                  for (@wp <- payCh) {
                    match wp {
                      (true, payment) => {
                        new zoneCh in {
                          accountZone!(currency, *zoneCh) |
                          for (@z <- zoneCh) {
                            match z {
                              (true, zone) => {
                                new lpCh in {
                                  @zone!("liquidate", victimOwnerId, payment, *lpCh) |
                                  for (@lp <- lpCh) {
                                    match lp {
                                      (true, revPayment) => {
                                        new revPurseCh in {
                                          accountEnsurePurse!("REV", *revPurseCh) |
                                          for (@rpc <- revPurseCh) {
                                            match rpc {
                                              (true, revPurse, revBrand) => {
                                                new depCh in {
                                                  @revPurse!("deposit", revPayment, *depCh) |
                                                  for (@d <- depCh) { ret!((true, amount)) }
                                                }
                                              }
                                              _ => ret!(rpc)
                                            }
                                          }
                                        }
                                      }
                                      _ => ret!(lp)
                                    }
                                  }
                                }
                              }
                              _ => ret!((false, "no zone"))
                            }
                          }
                        }
                      }
                      _ => ret!(wp)
                    }
                  }
                }
              }
              _ => ret!(pc)
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |

contract account(@"vaultInfo", deployerId, @currency, ret) = {
  new pkCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    for (@pk <- pkCh) {
      if (pk == pubKeyBytes) {
        new authCh in {
          accountVaultAuth!(currency, *authCh) |
          for (@a <- authCh) {
            match a {
              Nil => ret!((false, "open a vault first"))
              auth => {
                new zoneCh in {
                  accountZone!(currency, *zoneCh) |
                  for (@z <- zoneCh) {
                    match z {
                      (true, zone) => { @zone!("vault", ownerId, *ret) }
                      _ => ret!((false, "no zone"))
                    }
                  }
                }
              }
            }
          }
        }
      } else { ret!((false, "not owner")) }
    }
  }
} |
