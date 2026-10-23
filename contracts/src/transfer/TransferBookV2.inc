// TransferBook v0.2: one generic book per market.
//
// Captured by the deploy term: bookState, pool, AccountFactory, marketId, base, quote,
// baseIssuer, quoteIssuer, baseBrand, quoteBrand, escrowBase, escrowQuote, hash, bd.
//
// State: {marketId, base, quote, termsHash, paramsHash,
//         params: {defaultExpiryBlocks, maxExpiryBlocks}, active, paused,
//         transfers: Map(id -> {sender, source, dest, amount, claimHash, expiry, status}),
//         nextId, admins, threshold, govNonce}
// Claim/refund return the payment on ret; the caller's Account deposits it. Claims and
// refunds keep working after the market is paused or delisted.

contract bookNowV2(ret) = {
  new ch in { bd!(*ch) | for (@h, @s, @t <- ch) { ret!(h) } }
} |

contract bookRecordV2(@s, @source, @dest, @amount, @claimHash, @expiry, @sender, ret) = {
  match s.get("nextId") {
    id => {
      match s.get("transfers") {
        ts => {
          match ts.set(id, {
            "sender": sender, "source": source, "dest": dest, "amount": amount,
            "claimHash": claimHash, "expiry": expiry, "status": "open"
          }) {
            ts2 => {
              match s.set("transfers", ts2) {
                s2 => {
                  match s2.set("nextId", id + 1) { s3 => ret!((s3, id)) }
                }
              }
            }
          }
        }
      }
    }
  }
} |

contract bookSetStatusV2(@s, @id, @t, @status, ret) = {
  match t.set("status", status) {
    t2 => {
      match s.get("transfers") {
        ts => { match ts.set(id, t2) { ts2 => { match s.set("transfers", ts2) { s2 => ret!(s2) } } } }
      }
    }
  }
} |

contract bookTransferV2(@s, @id, ret) = {
  match s.get("transfers") {
    Nil => ret!(Nil)
    ts => { match ts.get(id) { Nil => ret!(Nil) t => ret!(t) } }
  }
} |

contract bookEscrowDepositV2(@dest, @payOut, ret) = {
  if (dest == base) { @escrowBase!("deposit", payOut, *ret) }
  else {
    if (dest == quote) { @escrowQuote!("deposit", payOut, *ret) }
    else { ret!((false, "bad asset")) }
  }
} |

contract bookEscrowWithdrawV2(@dest, @amount, ret) = {
  if (dest == base) { @escrowBase!("withdraw", (baseBrand, amount), *ret) }
  else {
    if (dest == quote) { @escrowQuote!("withdraw", (quoteBrand, amount), *ret) }
    else { ret!((false, "bad asset")) }
  }
} |

contract bookV2(@"quote", @sourceAsset, @destAsset, @amountIn, ret) = {
  if (sourceAsset == base && destAsset == quote) {
    @pool!("quote", base, amountIn, *ret)
  } else {
    if (sourceAsset == quote && destAsset == base) {
      @pool!("quote", quote, amountIn, *ret)
    } else { ret!((false, "unsupported pair")) }
  }
} |

contract bookV2(@"send", @sourceAsset, @destAsset, payment, @minDest, @claimHash, @expiry,
                @senderOwnerId, proof, ret) = {
  new pvCh, amtCh, swapCh, nowCh in {
    AccountFactory!("verify", senderOwnerId, *proof, *pvCh) |
    bookNowV2!(*nowCh) |
    if (sourceAsset == base) { @baseIssuer!("getAmountOf", *payment, *amtCh) }
    else { if (sourceAsset == quote) { @quoteIssuer!("getAmountOf", *payment, *amtCh) }
           else { amtCh!((false, "bad asset")) } } |
    for (@pv <- pvCh; @amt <- amtCh; @now <- nowCh) {
      match (pv, amt) {
        ((true, true), (true, amount)) => {
          if (amount <= 0) { ret!((false, "amount")) }
          else {
            if ((sourceAsset == base && destAsset == quote)
                || (sourceAsset == quote && destAsset == base)) {
              if (expiry <= now) { ret!((false, "expiry")) }
              else {
                for (@s <<- bookState) {
                  if (s.get("active") == false) { ret!((false, "market inactive")) }
                  else {
                    if (s.get("paused")) { ret!((false, "paused")) }
                    else {
                      if (expiry > now + s.get("params").get("maxExpiryBlocks")) {
                        ret!((false, "expiry too long"))
                      } else {
                        @pool!("swap", sourceAsset, *payment, minDest, *swapCh) |
                        for (@sr <- swapCh) {
                          match sr {
                            (true, out, payOut, fee) => {
                              new depCh in {
                                bookEscrowDepositV2!(destAsset, payOut, *depCh) |
                                for (@d <- depCh) {
                                  match d {
                                    (true, bal) => {
                                      new recCh in {
                                        bookRecordV2!(s, sourceAsset, destAsset, out, claimHash,
                                                      expiry, senderOwnerId, *recCh) |
                                        for (@rec <- recCh) {
                                          match rec { (ns, id) => { bookState!(ns) | ret!((true, id)) } }
                                        }
                                      }
                                    }
                                    _ => { bookState!(s) | ret!((false, "escrow deposit")) }
                                  }
                                }
                              }
                            }
                            _ => { bookState!(s) | ret!(sr) }
                          }
                        }
                      }
                    }
                  }
                }
              }
            } else { ret!((false, "unsupported pair")) }
          }
        }
        _ => ret!((false, "auth or payment"))
      }
    }
  }
} |

contract bookV2(@"claim", @transferId, @secret, ret) = {
  new hCh, nowCh in {
    hash!(secret, *hCh) |
    bookNowV2!(*nowCh) |
    for (@h <- hCh; @now <- nowCh) {
      for (@s <- bookState) {
        new tCh in {
          bookTransferV2!(s, transferId, *tCh) |
          for (@found <- tCh) {
            match found {
              Nil => { bookState!(s) | ret!((false, "no transfer")) }
              t => {
                match t.get("status") {
                  status => {
                    match t.get("expiry") {
                      expiry => {
                        match t.get("claimHash") {
                          ch => {
                            match t.get("dest") {
                              dest => {
                                match t.get("amount") {
                                  amount => {
                                    if (status == "open") {
                                      if (now > expiry) { bookState!(s) | ret!((false, "expired")) }
                                      else {
                                        if (h == ch) {
                                          new wdCh in {
                                            bookEscrowWithdrawV2!(dest, amount, *wdCh) |
                                            for (@w <- wdCh) {
                                              match w {
                                                (true, pay) => {
                                                  new stCh in {
                                                    bookSetStatusV2!(s, transferId, t, "claimed", *stCh) |
                                                    for (@ns <- stCh) {
                                                      bookState!(ns) | ret!((true, amount, pay))
                                                    }
                                                  }
                                                }
                                                _ => { bookState!(s) | ret!((false, "escrow withdraw")) }
                                              }
                                            }
                                          }
                                        } else { bookState!(s) | ret!((false, "bad secret")) }
                                      }
                                    } else { bookState!(s) | ret!((false, "not open")) }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
} |

contract bookV2(@"refund", @transferId, @senderOwnerId, proof, ret) = {
  new pvCh, nowCh in {
    AccountFactory!("verify", senderOwnerId, *proof, *pvCh) |
    bookNowV2!(*nowCh) |
    for (@pv <- pvCh; @now <- nowCh) {
      match pv {
        (true, true) => {
          for (@s <- bookState) {
            new tCh in {
              bookTransferV2!(s, transferId, *tCh) |
              for (@found <- tCh) {
                match found {
                  Nil => { bookState!(s) | ret!((false, "no transfer")) }
                  t => {
                    match t.get("status") {
                      status => {
                        match t.get("sender") {
                          sender => {
                            match t.get("expiry") {
                              expiry => {
                                match t.get("dest") {
                                  dest => {
                                    match t.get("amount") {
                                      amount => {
                                        if (status == "open") {
                                          if (sender != senderOwnerId) {
                                            bookState!(s) | ret!((false, "not sender"))
                                          } else {
                                            if (now <= expiry) {
                                              bookState!(s) | ret!((false, "not expired"))
                                            } else {
                                              new wdCh in {
                                                bookEscrowWithdrawV2!(dest, amount, *wdCh) |
                                                for (@w <- wdCh) {
                                                  match w {
                                                    (true, pay) => {
                                                      new stCh in {
                                                        bookSetStatusV2!(s, transferId, t, "refunded", *stCh) |
                                                        for (@ns <- stCh) {
                                                          bookState!(ns) | ret!((true, amount, pay))
                                                        }
                                                      }
                                                    }
                                                    _ => { bookState!(s) | ret!((false, "escrow withdraw")) }
                                                  }
                                                }
                                              }
                                            }
                                          }
                                        } else { bookState!(s) | ret!((false, "not open")) }
                                      }
                                    }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        _ => ret!((false, "auth"))
      }
    }
  }
} |

contract bookV2(@"info", @transferId, ret) = {
  for (@s <<- bookState) {
    match s.get("transfers") {
      Nil => ret!((false, "no transfers"))
      ts => { match ts.get(transferId) { Nil => ret!((false, "no transfer")) t => ret!((true, t)) } }
    }
  }
} |

contract bookV2(@"nextId", ret) = {
  for (@s <<- bookState) { ret!((true, s.get("nextId"))) }
} |

contract bookV2(@"pair", ret) = { ret!((true, base, quote)) } |

contract bookV2(@"terms", ret) = {
  for (@s <<- bookState) {
    ret!((true, {"marketId": s.get("marketId"), "termsHash": s.get("termsHash"),
                 "paramsHash": s.get("paramsHash"), "active": s.get("active"),
                 "paused": s.get("paused")}))
  }
} |

contract bookV2(@"escrows", ret) = {
  new bCh, qCh in {
    @escrowBase!("getCurrentAmount", *bCh) |
    @escrowQuote!("getCurrentAmount", *qCh) |
    for (@b <- bCh; @q <- qCh) { ret!((true, b, q)) }
  }
} |

contract bookAdminApplyV2(@action, @args, @nonce, ret) = {
  for (@s <- bookState) {
    if (nonce <= s.get("govNonce")) {
      bookState!(s) | ret!((false, "replay"))
    } else {
      if (action == "setActive") {
        match args.nth(0) { p => {
          bookState!(s.set("active", p == 1).set("govNonce", nonce)) | ret!((true, Nil))
        } }
      } else {
        if (action == "setPaused") {
          match args.nth(0) { p => {
            bookState!(s.set("paused", p == 1).set("govNonce", nonce)) | ret!((true, Nil))
          } }
        } else { bookState!(s) | ret!((false, "unknown action")) }
      }
    }
  }
} |

contract bookV2(@"admin", @nonce, @action, @args, @sigs, ret) = {
  for (@s <<- bookState) {
    match s.get("admins") {
      Nil => ret!((false, "no admins"))
      admins => {
        match s.get("threshold") {
          threshold => {
            match s.get("govNonce") {
              lastNonce => {
                if (nonce <= lastNonce) { ret!((false, "replay")) }
                else {
                  new okCh in {
                    verifyAdmin!("book:" ++ marketId, nonce, action, args, sigs, admins, threshold, *okCh) |
                    for (@ok <- okCh) {
                      if (ok) { bookAdminApplyV2!(action, args, nonce, *ret) }
                      else { ret!((false, "signatures")) }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
} |
