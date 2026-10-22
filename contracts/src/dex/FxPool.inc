// FxPool: oracle-anchored fixed-price market maker for one directed corridor (base -> quote).
//
// Captured by the factory: poolState, base, quote, baseBrand, baseIssuer, basePurse,
// quoteBrand, quoteIssuer, quotePurse, lpBrand, lpMint, lpIssuer, lpBurnFacet,
// OracleHub, Directory, admins, threshold, params.
//
// State: {base, quote, reserveBase, reserveQuote, totalShares, params, paused,
//         admins, threshold, govNonce}
// Amounts are base units (1e8/whole unit). Oracle rate = quote base-units per base base-unit x1e8.

contract poolRate(ret) = {
  new ch in {
    OracleHub!("getPair", base, quote, *ch) |
    for (@r <- ch) {
      match r {
        (true, m) => {
          match m.get("rate") {
            rate => { match m.get("fresh") { fresh => ret!((rate, fresh)) } }
          }
        }
        _ => ret!((0, false))
      }
    }
  }
} |

contract poolValue(@rb, @rq, @rate, ret) = {
  match ((rb * rate) / 100000000).toInt() {
    bv => ret!(bv + rq)
  }
} |

contract poolWeight(@rb, @rq, @rate, ret) = {
  new vCh in {
    poolValue!(rb, rq, rate, *vCh) |
    for (@v <- vCh) {
      if (v <= 0) { ret!(5000) }
      else {
        match ((((rb * rate) / 100000000).toInt() * 10000) / v).toInt() {
          w => ret!(w)
        }
      }
    }
  }
} |

contract poolFee(@weight, @params, ret) = {
  match params.get("baseSpreadBps") {
    baseFee => {
      match params.get("skewSpreadBps") {
        skewFee => {
          if (weight >= 5000) {
            match (((weight - 5000) * skewFee) / 5000).toInt() {
              extra => ret!(baseFee + extra)
            }
          } else {
            match (((5000 - weight) * skewFee) / 5000).toInt() {
              extra => ret!(baseFee + extra)
            }
          }
        }
      }
    }
  }
} |

// Out amount for a base-unit input. Direction: "b2q" or "q2b".
contract poolOut(@dir, @dx, @rate, @feeBps, ret) = {
  if (dir == "b2q") {
    match ((dx * rate) / 100000000).toInt() {
      gross => {
        match ((gross * (10000 - feeBps)) / 10000).toInt() {
          out => ret!(out)
        }
      }
    }
  } else {
    match ((dx * 100000000) / rate).toInt() {
      gross => {
        match ((gross * (10000 - feeBps)) / 10000).toInt() {
          out => ret!(out)
        }
      }
    }
  }
} |

contract poolUpdate(@s, @rb, @rq, @ts, @paused, @nonce, ret) = {
  match s.set("reserveBase", rb) {
    s1 => {
      match s1.set("reserveQuote", rq) {
        s2 => {
          match s2.set("totalShares", ts) {
            s3 => {
              match s3.set("paused", paused) {
                s4 => {
                  match s4.set("govNonce", nonce) {
                    s5 => ret!(s5)
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

contract poolAdminApply(@action, @args, @nonce, ret) = {
  for (@s <- poolState) {
    if (nonce <= s.get("govNonce")) {
      poolState!(s) | ret!((false, "replay"))
    } else {
      if (action == "setParams") {
        match args.nth(0) {
          baseFee => {
            match args.nth(1) {
              skewFee => {
                match args.nth(2) {
                  maxTrade => {
                    match s.set("params", {
                      "baseSpreadBps": baseFee, "skewSpreadBps": skewFee,
                      "maxTradeBps": maxTrade, "minLiquidity": 100000000
                    }) {
                      s1 => {
                        match s1.set("govNonce", nonce) {
                          s2 => { poolState!(s2) | ret!((true, Nil)) }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      } else {
        if (action == "setPaused") {
          match args.nth(0) {
            p => {
              match s.set("paused", p == 1) {
                s1 => {
                  match s1.set("govNonce", nonce) {
                    s2 => { poolState!(s2) | ret!((true, Nil)) }
                  }
                }
              }
            }
          }
        } else {
          poolState!(s) | ret!((false, "unknown action"))
        }
      }
    }
  }
} |

// Quote a swap. Reply (true, amountOut, feeBps, rate, maxIn) or (false, reason).
contract pool(@"quote", @assetIn, @amountIn, ret) = {
  new rateCh in {
    poolRate!(*rateCh) |
    for (@(rate, fresh) <- rateCh) {
      if (fresh == false) { ret!((false, "stale oracle")) }
      else {
        if (rate <= 0) { ret!((false, "no rate")) }
        else {
          for (@s <<- poolState) {
            if (s.get("paused")) { ret!((false, "paused")) }
            else {
              match s.get("params") {
                params => {
                  new wCh, fCh in {
                    poolWeight!(s.get("reserveBase"), s.get("reserveQuote"), rate, *wCh) |
                    for (@w <- wCh) {
                      poolFee!(w, params, *fCh) |
                      for (@fee <- fCh) {
                        if (assetIn == base) {
                          new oCh in {
                            poolOut!("b2q", amountIn, rate, fee, *oCh) |
                            for (@out <- oCh) {
                              match ((s.get("reserveBase") * params.get("maxTradeBps")) / 10000).toInt() {
                                maxIn => ret!((true, out, fee, rate, maxIn))
                              }
                            }
                          }
                        } else {
                          if (assetIn == quote) {
                            new oCh in {
                              poolOut!("q2b", amountIn, rate, fee, *oCh) |
                              for (@out <- oCh) {
                                match ((s.get("reserveQuote") * params.get("maxTradeBps")) / 10000).toInt() {
                                  maxIn => ret!((true, out, fee, rate, maxIn))
                                }
                              }
                            }
                          } else { ret!((false, "unknown asset")) }
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

// Quote the exact quote-side amount matching a base-side deposit (current ratio).
contract pool(@"quoteAdd", @baseAmount, ret) = {
  for (@s <<- poolState) {
    new rateCh in {
      poolRate!(*rateCh) |
      for (@(rate, fresh) <- rateCh) {
        if (fresh == false) { ret!((false, "stale oracle")) }
        else {
          if (s.get("totalShares") == 0) {
            match ((baseAmount * rate) / 100000000).toInt() {
              q => ret!((true, baseAmount, q))
            }
          } else {
            if (s.get("reserveBase") <= 0) { ret!((false, "empty pool")) }
            else {
              match ((baseAmount * s.get("reserveQuote")) / s.get("reserveBase")).toInt() {
                q => ret!((true, baseAmount, q))
              }
            }
          }
        }
      }
    }
  }
} |

contract pool(@"addLiquidity", @basePayment, @quotePayment, @minShares, ret) = {
  new bCh, qCh, rateCh, bdAF, qdAF, minDepAF, bdAS, qdAS in {
    @baseIssuer!("getAmountOf", basePayment, *bCh) |
    @quoteIssuer!("getAmountOf", quotePayment, *qCh) |
    poolRate!(*rateCh) |
    for (@b <- bCh; @q <- qCh; @(rate, fresh) <- rateCh) {
      match (b, q) {
        ((true, baseAmount), (true, quoteAmount)) => {
          if (baseAmount <= 0) { ret!((false, "base amount")) }
          else {
            if (quoteAmount <= 0) { ret!((false, "quote amount")) }
            else {
              if (fresh == false) { ret!((false, "stale oracle")) }
              else {
                if (rate <= 0) { ret!((false, "no rate")) }
                else {
                  for (@s <- poolState) {
                    if (s.get("paused")) { poolState!(s) | ret!((false, "paused")) }
                    else {
                      new vCh in {
                        poolValue!(baseAmount, quoteAmount, rate, *vCh) |
                        for (@depositValue <- vCh) {
                          if (s.get("totalShares") == 0) {
                            // First deposit: require the value to be roughly balanced.
                            new bvCh in {
                              match ((baseAmount * rate) / 100000000).toInt() {
                                bv => {
                                  if (bv * 100 < quoteAmount * 99 || bv * 100 > quoteAmount * 101) {
                                    poolState!(s) | ret!((false, "first deposit must match the oracle ratio"))
                                  } else {
                                    match depositValue - 100000000 {
                                      shares => {
                                        if (shares <= 0) { poolState!(s) | ret!((false, "too small")) }
                                        else {
                                          new newStateChAF in {
                                            poolUpdate!(s, baseAmount, quoteAmount, shares + 100000000,
                                                        s.get("paused"), s.get("govNonce"), *newStateChAF) |
                                            for (@nsAF <- newStateChAF) {
                                              poolState!(nsAF) |
                                              @basePurse!("deposit", basePayment, *bdAF) |
                                              for (@_ <- bdAF) {
                                                @quotePurse!("deposit", quotePayment, *qdAF) |
                                                for (@_ <- qdAF) {
                                                  new minChAF in {
                                                    @lpMint!("mintPayment", (lpBrand, 100000000), *minChAF) |
                                                    for (@(true, minPay) <- minChAF) {
                                                      @lpBurnFacet!("deposit", minPay, *minDepAF) |
                                                      for (@_ <- minDepAF) {
                                                        new lpChAF in {
                                                          @lpMint!("mintPayment", (lpBrand, shares), *lpChAF) |
                                                          for (@(true, lpPay) <- lpChAF) {
                                                            ret!((true, shares, lpPay))
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
                          } else {
                            new poolVCh in {
                              poolValue!(s.get("reserveBase"), s.get("reserveQuote"), rate, *poolVCh) |
                              for (@poolV <- poolVCh) {
                                if (poolV <= 0) { poolState!(s) | ret!((false, "empty pool")) }
                                else {
                                  match ((depositValue * s.get("totalShares")) / poolV).toInt() {
                                    shares => {
                                      if (shares < minShares) { poolState!(s) | ret!((false, "slippage")) }
                                      else {
                                        new newStateChAS in {
                                          poolUpdate!(s, s.get("reserveBase") + baseAmount,
                                                      s.get("reserveQuote") + quoteAmount,
                                                      s.get("totalShares") + shares,
                                                      s.get("paused"), s.get("govNonce"), *newStateChAS) |
                                          for (@nsAS <- newStateChAS) {
                                            poolState!(nsAS) |
                                            @basePurse!("deposit", basePayment, *bdAS) |
                                            for (@_ <- bdAS) {
                                              @quotePurse!("deposit", quotePayment, *qdAS) |
                                              for (@_ <- qdAS) {
                                                new lpChAS in {
                                                  @lpMint!("mintPayment", (lpBrand, shares), *lpChAS) |
                                                  for (@(true, lpPay) <- lpChAS) {
                                                    ret!((true, shares, lpPay))
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
                }
              }
            }
          }
        }
        _ => ret!((false, "bad payments"))
      }
    }
  }
} |

contract pool(@"removeLiquidity", @lpPayment, @minBase, @minQuote, ret) = {
  new amtCh, bdR in {
    @lpIssuer!("getAmountOf", lpPayment, *amtCh) |
    for (@a <- amtCh) {
      match a {
        (true, shares) => {
          if (shares <= 0) { ret!((false, "shares")) }
          else {
            for (@s <- poolState) {
              if (shares > s.get("totalShares")) { poolState!(s) | ret!((false, "too many shares")) }
              else {
                match ((shares * s.get("reserveBase")) / s.get("totalShares")).toInt() {
                  baseOut => {
                    match ((shares * s.get("reserveQuote")) / s.get("totalShares")).toInt() {
                      quoteOut => {
                        if (baseOut < minBase) { poolState!(s) | ret!((false, "base slippage")) }
                        else {
                          if (quoteOut < minQuote) { poolState!(s) | ret!((false, "quote slippage")) }
                          else {
                            new newStateChR in {
                              poolUpdate!(s, s.get("reserveBase") - baseOut,
                                          s.get("reserveQuote") - quoteOut,
                                          s.get("totalShares") - shares,
                                          s.get("paused"), s.get("govNonce"), *newStateChR) |
                              for (@nsR <- newStateChR) {
                                poolState!(nsR) |
                                @lpBurnFacet!("deposit", lpPayment, *bdR) |
                                for (@_ <- bdR) {
                                  new bPayChR, qPayChR in {
                                    @basePurse!("withdraw", (baseBrand, baseOut), *bPayChR) |
                                    @quotePurse!("withdraw", (quoteBrand, quoteOut), *qPayChR) |
                                    for (@(true, basePay) <- bPayChR; @(true, quotePay) <- qPayChR) {
                                      ret!((true, basePay, quotePay, shares))
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
        _ => ret!((false, "not an LP payment"))
      }
    }
  }
} |

contract pool(@"swap", @assetIn, payment, @minOut, ret) = {
  if (assetIn == base) {
    new amtCh, rateCh, bdB in {
      @baseIssuer!("getAmountOf", *payment, *amtCh) |
      poolRate!(*rateCh) |
      for (@a <- amtCh; @(rate, fresh) <- rateCh) {
        match a {
          (true, dx) => {
            if (dx <= 0) { ret!((false, "amount")) }
            else {
              if (fresh == false) { ret!((false, "stale oracle")) }
              else {
                if (rate <= 0) { ret!((false, "no rate")) }
                else {
                  for (@s <- poolState) {
                    if (s.get("paused")) { poolState!(s) | ret!((false, "paused")) }
                    else {
                      match s.get("params") {
                        params => {
                          if (dx * 10000 > s.get("reserveBase") * params.get("maxTradeBps")) {
                            poolState!(s) | ret!((false, "above max trade"))
                          } else {
                            new wCh, fCh in {
                              poolWeight!(s.get("reserveBase"), s.get("reserveQuote"), rate, *wCh) |
                              for (@w <- wCh) {
                                poolFee!(w, params, *fCh) |
                                for (@fee <- fCh) {
                                  new oCh in {
                                    poolOut!("b2q", dx, rate, fee, *oCh) |
                                    for (@out <- oCh) {
                                      if (out <= 0) { poolState!(s) | ret!((false, "zero out")) }
                                      else {
                                        if (out < minOut) { poolState!(s) | ret!((false, "slippage")) }
                                        else {
                                          if (out >= s.get("reserveQuote")) { poolState!(s) | ret!((false, "insufficient liquidity")) }
                                          else {
                                            new newStateChB in {
                                              poolUpdate!(s, s.get("reserveBase") + dx,
                                                          s.get("reserveQuote") - out,
                                                          s.get("totalShares"),
                                                          s.get("paused"), s.get("govNonce"), *newStateChB) |
                                              for (@nsB <- newStateChB) {
                                                poolState!(nsB) |
                                                @basePurse!("deposit", *payment, *bdB) |
                                                for (@_ <- bdB) {
                                                  new outChB in {
                                                    @quotePurse!("withdraw", (quoteBrand, out), *outChB) |
                                                    for (@(true, payOut) <- outChB) {
                                                      ret!((true, out, payOut, fee))
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
                  }
                }
              }
            }
          }
          _ => ret!((false, "not a base payment"))
        }
      }
    }
  } else {
    if (assetIn == quote) {
      new amtCh, rateCh, bdQ in {
        @quoteIssuer!("getAmountOf", *payment, *amtCh) |
        poolRate!(*rateCh) |
        for (@a <- amtCh; @(rate, fresh) <- rateCh) {
          match a {
            (true, dx) => {
              if (dx <= 0) { ret!((false, "amount")) }
              else {
                if (fresh == false) { ret!((false, "stale oracle")) }
                else {
                  if (rate <= 0) { ret!((false, "no rate")) }
                  else {
                    for (@s <- poolState) {
                      if (s.get("paused")) { poolState!(s) | ret!((false, "paused")) }
                      else {
                        match s.get("params") {
                          params => {
                            if (dx * 10000 > s.get("reserveQuote") * params.get("maxTradeBps")) {
                              poolState!(s) | ret!((false, "above max trade"))
                            } else {
                              new wCh, fCh in {
                                poolWeight!(s.get("reserveBase"), s.get("reserveQuote"), rate, *wCh) |
                                for (@w <- wCh) {
                                  poolFee!(w, params, *fCh) |
                                  for (@fee <- fCh) {
                                    new oCh in {
                                      poolOut!("q2b", dx, rate, fee, *oCh) |
                                      for (@out <- oCh) {
                                        if (out <= 0) { poolState!(s) | ret!((false, "zero out")) }
                                        else {
                                          if (out < minOut) { poolState!(s) | ret!((false, "slippage")) }
                                          else {
                                            if (out >= s.get("reserveBase")) { poolState!(s) | ret!((false, "insufficient liquidity")) }
                                            else {
                                              new newStateChQ in {
                                                poolUpdate!(s, s.get("reserveBase") - out,
                                                            s.get("reserveQuote") + dx,
                                                            s.get("totalShares"),
                                                            s.get("paused"), s.get("govNonce"), *newStateChQ) |
                                                for (@nsQ <- newStateChQ) {
                                                  poolState!(nsQ) |
                                                  @quotePurse!("deposit", *payment, *bdQ) |
                                                  for (@_ <- bdQ) {
                                                    new outChQ in {
                                                      @basePurse!("withdraw", (baseBrand, out), *outChQ) |
                                                      for (@(true, payOut) <- outChQ) {
                                                        ret!((true, out, payOut, fee))
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
                    }
                  }
                }
              }
            }
            _ => ret!((false, "not a quote payment"))
          }
        }
      }
    } else { ret!((false, "unknown asset")) }
  }
} |

contract pool(@"reserves", ret) = {
  for (@s <<- poolState) {
    new rateCh in {
      poolRate!(*rateCh) |
      for (@(rate, fresh) <- rateCh) {
        ret!((true, s.get("reserveBase"), s.get("reserveQuote"),
              s.get("totalShares"), rate, fresh, s.get("paused")))
      }
    }
  }
} |

contract pool(@"lpAsset", ret) = { ret!((true, lpBrand, lpIssuer)) } |

contract pool(@"params", ret) = {
  for (@s <<- poolState) { ret!((true, s.get("params"))) }
} |

contract pool(@"pair", ret) = { ret!((true, base, quote)) } |

contract pool(@"admin", @nonce, @action, @args, @sigs, ret) = {
  for (@s <<- poolState) {
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
                    verifyAdmin!("pool:" ++ base ++ "/" ++ quote ++ ":fpmm",
                                 nonce, action, args, sigs, admins, threshold, *okCh) |
                    for (@ok <- okCh) {
                      if (ok) { poolAdminApply!(action, args, nonce, *ret) }
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
