// OracleHub: signed reporter prices, median/freshness/spread decisions, M-of-N admin.
//
// State (seeded by the bootstrap):
//   {reporters: [pubKeyBytes x3], prices: Map(currency -> Map(index -> {price,height})),
//    params: {quorum, maxAgeBlocks, maxSpreadBps, minPrice, maxPrice},
//    admins: [pubKeyBytes], threshold: Int, govNonce: Int}
//
// Captured: oracleState, bd (`rho:block:data`), hash, verify, Guard helpers.

contract oracleNow(ret) = {
  new ch in {
    bd!(*ch) |
    for (@h, @sender, @ts <- ch) { ret!(h) }
  }
} |

contract oracleEntry(@currency, @index, ret) = {
  for (@s <<- oracleState) {
    match s.get("prices") {
      Nil => ret!(Nil)
      prices => {
        match prices.get(currency) {
          Nil => ret!(Nil)
          byIndex => {
            match byIndex.get(index) {
              Nil => ret!(Nil)
              entry => ret!(entry)
            }
          }
        }
      }
    }
  }
} |

contract oracleValue(@entry, ret) = {
  match entry {
    Nil => ret!((0, 0))
    e => {
      match e.get("price") {
        p => {
          match e.get("height") { h => ret!((p, h)) }
        }
      }
    }
  }
} |

contract oracleMedian3(@a, @b, @c, ret) = {
  if (a < b) {
    if (b < c) { ret!(b) }
    else { if (a < c) { ret!(c) } else { ret!(a) } }
  } else {
    if (a < c) { ret!(a) }
    else { if (b < c) { ret!(c) } else { ret!(b) } }
  }
} |

contract oracleMax3(@a, @b, @c, ret) = {
  if (a >= b) {
    if (a >= c) { ret!(a) } else { ret!(c) }
  } else {
    if (b >= c) { ret!(b) } else { ret!(c) }
  }
} |

contract oracleMin3(@a, @b, @c, ret) = {
  if (a <= b) {
    if (a <= c) { ret!(a) } else { ret!(c) }
  } else {
    if (b <= c) { ret!(b) } else { ret!(c) }
  }
} |

contract oracleIsFresh(@price, @height, @now, @maxAge, @minP, @maxP, ret) = {
  if (height <= 0) { ret!(false) }
  else {
    if (height > now) { ret!(false) }
    else {
      if ((now - height) > maxAge) { ret!(false) }
      else {
        if (price < minP) { ret!(false) }
        else { if (price > maxP) { ret!(false) } else { ret!(true) } }
      }
    }
  }
} |

contract oracleB2I(@b, ret) = {
  if (b) { ret!(1) } else { ret!(0) }
} |

contract oracleDecide(@count, @quorum, @spread, @median, @spreadBps, @minP, @maxP, ret) = {
  if (count < quorum) { ret!(false) }
  else {
    if (median <= 0) { ret!(false) }
    else {
      if (median < minP) { ret!(false) }
      else {
        if (median > maxP) { ret!(false) }
        else {
          if ((spread * 10000) > (median * spreadBps)) { ret!(false) } else { ret!(true) }
        }
      }
    }
  }
} |

contract oracleStore(@currency, @index, @price, @height, ret) = {
  for (@s <- oracleState) {
    match s.get("prices") {
      Nil => { oracleState!(s) | ret!((false, "no prices map")) }
      prices => {
        match prices.get(currency) {
          Nil => {
            oracleState!(s.set("prices", prices.set(currency, {index: {"price": price, "height": height}}))) |
            ret!((true, Nil))
          }
          byIndex => {
            match byIndex.get(index) {
              Nil => {
                oracleState!(s.set("prices", prices.set(currency, byIndex.set(index, {"price": price, "height": height})))) |
                ret!((true, Nil))
              }
              old => {
                match old.get("height") {
                  oldH => {
                    if (height > oldH) {
                      oracleState!(s.set("prices", prices.set(currency, byIndex.set(index, {"price": price, "height": height})))) |
                      ret!((true, Nil))
                    } else {
                      oracleState!(s) | ret!((false, "height not monotonic"))
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

contract oracleAdminApply(@action, @args, @nonce, ret) = {
  for (@s <- oracleState) {
    if (nonce <= s.get("govNonce")) {
      // Re-check under the consumed state so two concurrent actions cannot reuse a nonce.
      oracleState!(s) | ret!((false, "replay"))
    } else {
    if (action == "setParams") {
      match args.nth(0) {
        q => {
          match args.nth(1) {
            age => {
              match args.nth(2) {
                spread => {
                  match args.nth(3) {
                    minP => {
                      match args.nth(4) {
                        maxP => {
                          match s.set("params", {
                            "quorum": q, "maxAgeBlocks": age, "maxSpreadBps": spread,
                            "minPrice": minP, "maxPrice": maxP
                          }) {
                            s1 => {
                              match s1.set("govNonce", nonce) {
                                s2 => { oracleState!(s2) | ret!((true, Nil)) }
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
      if (action == "setReporters") {
        match args.nth(0) {
          a0 => {
            match args.nth(1) {
              a1 => {
                match args.nth(2) {
                  a2 => {
                    match s.set("reporters", [a0.hexToBytes(), a1.hexToBytes(), a2.hexToBytes()]) {
                      s1 => {
                        match s1.set("govNonce", nonce) {
                          s2 => { oracleState!(s2) | ret!((true, Nil)) }
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
        oracleState!(s) | ret!((false, "unknown action"))
      }
    }
    }
  }
} |

contract OracleHub(@"get", @currency, ret) = {
  new nowCh, e0Ch, e1Ch, e2Ch, v0Ch, v1Ch, v2Ch in {
    oracleNow!(*nowCh) |
    oracleEntry!(currency, 0, *e0Ch) |
    oracleEntry!(currency, 1, *e1Ch) |
    oracleEntry!(currency, 2, *e2Ch) |
    for (@now <- nowCh; @e0 <- e0Ch; @e1 <- e1Ch; @e2 <- e2Ch) {
      oracleValue!(e0, *v0Ch) |
      oracleValue!(e1, *v1Ch) |
      oracleValue!(e2, *v2Ch) |
      for (@(p0, h0) <- v0Ch; @(p1, h1) <- v1Ch; @(p2, h2) <- v2Ch) {
        for (@s <<- oracleState) {
          match s.get("params") {
            Nil => ret!((false, "no params"))
            params => {
              match params.get("quorum") {
                quorum => {
                  match params.get("maxAgeBlocks") {
                    maxAge => {
                      match params.get("maxSpreadBps") {
                        spreadBps => {
                          match params.get("minPrice") {
                            minP => {
                              match params.get("maxPrice") {
                                maxP => {
                                  new f0Ch, f1Ch, f2Ch in {
                                    oracleIsFresh!(p0, h0, now, maxAge, minP, maxP, *f0Ch) |
                                    oracleIsFresh!(p1, h1, now, maxAge, minP, maxP, *f1Ch) |
                                    oracleIsFresh!(p2, h2, now, maxAge, minP, maxP, *f2Ch) |
                                    for (@f0 <- f0Ch; @f1 <- f1Ch; @f2 <- f2Ch) {
                                      new i0Ch, i1Ch, i2Ch in {
                                        oracleB2I!(f0, *i0Ch) |
                                        oracleB2I!(f1, *i1Ch) |
                                        oracleB2I!(f2, *i2Ch) |
                                        for (@i0 <- i0Ch; @i1 <- i1Ch; @i2 <- i2Ch) {
                                          new medianCh, maxHCh, maxPCh, minPCh in {
                                            oracleMedian3!(p0, p1, p2, *medianCh) |
                                            oracleMax3!(h0, h1, h2, *maxHCh) |
                                            oracleMax3!(p0, p1, p2, *maxPCh) |
                                            oracleMin3!(p0, p1, p2, *minPCh) |
                                            for (@median <- medianCh; @maxH <- maxHCh;
                                                 @pMax <- maxPCh; @pMin <- minPCh) {
                                              new okCh in {
                                                oracleDecide!(i0 + i1 + i2, quorum, pMax - pMin,
                                                              median, spreadBps, minP, maxP, *okCh) |
                                                for (@ok <- okCh) {
                                                  if (ok) {
                                                    ret!((true, {"price": median, "height": maxH,
                                                                 "fresh": true, "reason": "ok"}))
                                                  } else {
                                                    ret!((true, {"price": median, "height": maxH,
                                                                 "fresh": false, "reason": "quorum/spread/band"}))
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
      }
    }
  }
} |

contract oraclePairReply(@fb, @fq, @pbase, @pquote, ret) = {
  if (fb) {
    if (fq) {
      if (pquote > 0) {
        match (pbase * 100000000) / pquote {
          Int => ret!((true, {"rate": (pbase * 100000000) / pquote, "fresh": true, "reason": "ok"}))
          _ => ret!((false, "rate overflow"))
        }
      } else { ret!((true, {"rate": 0, "fresh": false, "reason": "zero quote"})) }
    } else { ret!((true, {"rate": 0, "fresh": false, "reason": "stale quote"})) }
  } else { ret!((true, {"rate": 0, "fresh": false, "reason": "stale base"})) }
} |

contract OracleHub(@"getPair", @base, @quote, ret) = {
  new bCh, qCh in {
    OracleHub!("get", base, *bCh) |
    OracleHub!("get", quote, *qCh) |
    for (@rb <- bCh; @rq <- qCh) {
      match rb {
        (true, pb) => {
          match rq {
            (true, pq) => {
              match pb.get("fresh") {
                fb => {
                  match pq.get("fresh") {
                    fq => {
                      match pb.get("price") {
                        pbase => {
                          match pq.get("price") {
                            pquote => oraclePairReply!(fb, fq, pbase, pquote, *ret)
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            _ => ret!((false, "quote feed error"))
          }
        }
        _ => ret!((false, "base feed error"))
      }
    }
  }
} |

contract OracleHub(@"submit", @currency, @price, @height, @index, @pubKey, @sig, ret) = {
  new nowCh in {
    oracleNow!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <<- oracleState) {
        match s.get("reporters") {
          Nil => ret!((false, "no reporters"))
          reporters => {
            if (index < 0) { ret!((false, "bad index")) }
            else {
              if (index >= reporters.length()) { ret!((false, "bad index")) }
              else {
                match reporters.nth(index) {
                  allowed => {
                    if (allowed == pubKey) {
                      if (height > now) { ret!((false, "future height")) }
                      else {
                        if ((now - height) > 1000) { ret!((false, "stale height")) }
                        else {
                          new hashCh, vCh in {
                            match "rcash:oracle:v1|/root|" ++ currency ++ "|" ++ price.toString() ++ "|" ++ height.toString() {
                              payload => {
                                hash!(payload.toUtf8Bytes(), *hashCh) |
                                for (@digest <- hashCh) {
                                  verify!(digest, sig, pubKey, *vCh) |
                                  for (@ok <- vCh) {
                                    if (ok) { oracleStore!(currency, index, price, height, *ret) }
                                    else { ret!((false, "bad signature")) }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    } else { ret!((false, "not the reporter at that index")) }
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

contract OracleHub(@"reporters", ret) = {
  for (@s <<- oracleState) {
    match s.get("reporters") {
      Nil => ret!((false, "no reporters"))
      reporters => ret!((true, reporters))
    }
  }
} |

contract OracleHub(@"admin", @nonce, @action, @args, @sigs, ret) = {
  for (@s <<- oracleState) {
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
                    verifyAdmin!("oracle", nonce, action, args, sigs, admins, threshold, *okCh) |
                    for (@ok <- okCh) {
                      if (ok) { oracleAdminApply!(action, args, nonce, *ret) }
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
