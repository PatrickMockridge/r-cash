// OracleHub v0.2: per-currency feeds, a global reporter allowlist, liveness trials.
//
// State:
//   {allowlist: [pubKeyBytes],
//    keyUse: Map(hex -> Int),
//    feeds: Map(currency -> {reporters:[k0,k1,k2], sponsor, quorum, maxAgeBlocks,
//                           maxSpreadBps, minPrice, maxPrice, policyHash,
//                           trialStart, trialBlocks, trialMinSubmits,
//                           seen0, seen1, seen2, trialSubmits, active, paused, listedAt}),
//    prices: Map(currency -> Map(index -> {price, height})),
//    params: {quorum, maxAgeBlocks, maxSpreadBps, minPrice, maxPrice},
//    admins, threshold, govNonce}
//
// Captured: oracleState, bd, hash, verify, ListingRegistry, Guard helpers.
// One feed has exactly three reporters; quorum is 2. A currency lists only if the
// listing registry knows it. The sponsor may be at most one of the three reporters.

contract oracleNowV2(ret) = {
  new ch in {
    bd!(*ch) |
    for (@h, @sender, @ts <- ch) { ret!(h) }
  }
} |

contract oracleB2IV2(@b, ret) = {
  if (b) { ret!(1) } else { ret!(0) }
} |

contract oracleInList(@items, @i, @key, ret) = {
  if (i >= items.length()) { ret!(false) }
  else {
    match items.nth(i) {
      x => {
        if (x == key) { ret!(true) }
        else { oracleInList!(items, i + 1, key, *ret) }
      }
    }
  }
} |

contract oracleListRemove(@items, @i, @key, @acc, ret) = {
  if (i >= items.length()) { ret!(acc) }
  else {
    match items.nth(i) {
      x => {
        if (x == key) { oracleListRemove!(items, i + 1, key, acc, *ret) }
        else { oracleListRemove!(items, i + 1, key, acc ++ [x], *ret) }
      }
    }
  }
} |

contract oracleFeedOf(@currency, ret) = {
  for (@s <<- oracleState) {
    match s.get("feeds") {
      Nil => ret!(Nil)
      feeds => {
        match feeds.get(currency) {
          Nil => ret!(Nil)
          feed => ret!(feed)
        }
      }
    }
  }
} |

contract oracleEntryOf(@currency, @index, ret) = {
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

contract oracleValueV2(@entry, ret) = {
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

contract oracleMedian3V2(@a, @b, @c, ret) = {
  if (a < b) {
    if (b < c) { ret!(b) }
    else { if (a < c) { ret!(c) } else { ret!(a) } }
  } else {
    if (a < c) { ret!(a) }
    else { if (b < c) { ret!(c) } else { ret!(b) } }
  }
} |

contract oracleMax3V2(@a, @b, @c, ret) = {
  if (a >= b) {
    if (a >= c) { ret!(a) } else { ret!(c) }
  } else {
    if (b >= c) { ret!(b) } else { ret!(c) }
  }
} |

contract oracleMin3V2(@a, @b, @c, ret) = {
  if (a <= b) {
    if (a <= c) { ret!(a) } else { ret!(c) }
  } else {
    if (b <= c) { ret!(b) } else { ret!(c) }
  }
} |

contract oracleIsFreshV2(@price, @height, @now, @maxAge, @minP, @maxP, ret) = {
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

contract oracleDecideV2(@count, @quorum, @spread, @median, @spreadBps, @minP, @maxP, ret) = {
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

contract oracleMarkSeen(@feed, @index, ret) = {
  if (index == 0) { ret!(feed.set("seen0", true)) }
  else {
    if (index == 1) { ret!(feed.set("seen1", true)) }
    else { ret!(feed.set("seen2", true)) }
  }
} |

contract oracleCountSeen(@feed, ret) = {
  new c0, c1, c2 in {
    oracleB2IV2!(feed.get("seen0"), *c0) |
    oracleB2IV2!(feed.get("seen1"), *c1) |
    oracleB2IV2!(feed.get("seen2"), *c2) |
    for (@a <- c0; @b <- c1; @c <- c2) { ret!(a + b + c) }
  }
} |

contract oraclePolicyHashV2(@quorum, @age, @spread, @minP, @maxP, @tb, @tms, ret) = {
  termsHash!(*hash, "rcash:oracle-policy:v1",
             [quorum, age, spread, minP, maxP, tb, tms], *ret)
} |

contract oracleFeedPayload(@currency, @k0, @k1, @k2, @sponsor, @quorum, @age, @spread,
                           @minP, @maxP, @tb, @tms, ret) = {
  ret!("rcash:oracle-feed:v1|/root|" ++ currency ++ "|" ++ k0 ++ "|" ++ k1 ++ "|" ++ k2
       ++ "|" ++ sponsor ++ "|" ++ quorum.toString() ++ "|" ++ age.toString()
       ++ "|" ++ spread.toString() ++ "|" ++ minP.toString() ++ "|" ++ maxP.toString()
       ++ "|" ++ tb.toString() ++ "|" ++ tms.toString())
} |

// Store a price and, while inactive, count trial participation. Consumes state once.
contract oracleStoreV2(@currency, @index, @price, @height, ret) = {
  for (@s <- oracleState) {
    match s.get("feeds") {
      Nil => { oracleState!(s) | ret!((false, "no feeds")) }
      feeds => {
        match feeds.get(currency) {
          Nil => { oracleState!(s) | ret!((false, "no feed")) }
          feed => {
            if (feed.get("paused")) {
              oracleState!(s) | ret!((false, "feed paused"))
            } else {
              match s.get("prices") {
                Nil => { oracleState!(s) | ret!((false, "no prices")) }
                prices => {
                  match prices.get(currency) {
                    Nil => {
                      new trialCh in {
                        oracleMarkSeen!(feed, index, *trialCh) |
                        for (@f1 <- trialCh) {
                          match f1.get("trialSubmits") {
                            n => {
                              match f1.set("trialSubmits", n + 1) {
                                f2 => {
                                  oracleState!(s.set("prices",
                                    prices.set(currency, {index: {"price": price, "height": height}}))
                                    .set("feeds", feeds.set(currency, f2))) |
                                  ret!((true, Nil))
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                    byIndex => {
                      match byIndex.get(index) {
                        Nil => {
                          new trialCh2 in {
                            oracleMarkSeen!(feed, index, *trialCh2) |
                            for (@f1 <- trialCh2) {
                              match f1.get("trialSubmits") {
                                n2 => {
                                  match f1.set("trialSubmits", n2 + 1) {
                                    f2 => {
                                      oracleState!(s.set("prices",
                                        prices.set(currency, byIndex.set(index, {"price": price, "height": height})))
                                        .set("feeds", feeds.set(currency, f2))) |
                                      ret!((true, Nil))
                                    }
                                  }
                                }
                              }
                            }
                          }
                        }
                        old => {
                          match old.get("height") {
                            oldH => {
                              if (height > oldH) {
                                new trialCh3 in {
                                  oracleMarkSeen!(feed, index, *trialCh3) |
                                  for (@f1 <- trialCh3) {
                                    match f1.get("trialSubmits") {
                                      n3 => {
                                        match f1.set("trialSubmits", n3 + 1) {
                                          f2 => {
                                            oracleState!(s.set("prices",
                                              prices.set(currency, byIndex.set(index, {"price": price, "height": height})))
                                              .set("feeds", feeds.set(currency, f2))) |
                                            ret!((true, Nil))
                                          }
                                        }
                                      }
                                    }
                                  }
                                }
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
          }
        }
      }
    }
  }
} |

// Open a feed. Permissionless with the sponsor's signature; the three reporters must be
// on the global allowlist, distinct, and at most one may be the sponsor.
contract OracleHubV2(@"openFeed", @currency, @k0Hex, @k1Hex, @k2Hex, @sponsorHex, @sig,
                      @quorum, @age, @spread, @minP, @maxP, @tb, @tms, ret) = {
  new k0Ch, k1Ch, k2Ch, spCh, curCh, payloadCh, digCh, okCh in {
    match k0Hex.hexToBytes() { k0 => k0Ch!(k0) } |
    match k1Hex.hexToBytes() { k1 => k1Ch!(k1) } |
    match k2Hex.hexToBytes() { k2 => k2Ch!(k2) } |
    match sponsorHex.hexToBytes() { sp => spCh!(sp) } |
    ListingRegistry!("currency", currency, *curCh) |
    oracleFeedPayload!(currency, k0Hex, k1Hex, k2Hex, sponsorHex, quorum, age, spread,
                       minP, maxP, tb, tms, *payloadCh) |
    for (@k0 <- k0Ch; @k1 <- k1Ch; @k2 <- k2Ch; @sp <- spCh; @cur <- curCh;
         @payload <- payloadCh) {
      match cur {
        (true, record) => {
          if (record.get("status") != "active") { ret!((false, "currency not active")) }
          else {
            if (quorum != 2) { ret!((false, "quorum")) }
            else {
              if (age < 5 || age > 1000) { ret!((false, "max age")) }
              else {
                if (spread < 50 || spread > 1000) { ret!((false, "spread")) }
                else {
                  if (minP < 1 || maxP > 1000000000000 || minP >= maxP) { ret!((false, "band")) }
                  else {
                    if (tb < 10 || tb > 43200 || tms < 4 || tms > 10000) { ret!((false, "trial")) }
                    else {
                      if (k0 == k1 || k0 == k2 || k1 == k2) { ret!((false, "reporters")) }
                      else {
                        if (k0Hex == sponsorHex || k1Hex == sponsorHex || k2Hex == sponsorHex) {
                          // at most one sponsor key is allowed; two or three is a conflict
                          if ((k0Hex == sponsorHex && k1Hex == sponsorHex)
                              || (k0Hex == sponsorHex && k2Hex == sponsorHex)
                              || (k1Hex == sponsorHex && k2Hex == sponsorHex)) {
                            ret!((false, "sponsor conflict"))
                          } else { oracleOpenFeedStore!(currency, k0, k1, k2, k0Hex, k1Hex, k2Hex, sp, sponsorHex,
                                                        quorum, age, spread, minP, maxP, tb, tms,
                                                        payload, sig, *ret) }
                        } else {
                          oracleOpenFeedStore!(currency, k0, k1, k2, k0Hex, k1Hex, k2Hex, sp, sponsorHex,
                                               quorum, age, spread, minP, maxP, tb, tms,
                                               payload, sig, *ret)
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        _ => ret!((false, "unknown currency"))
      }
    }
  }
} |

contract oracleOpenFeedStore(@currency, @k0, @k1, @k2, @k0Hex, @k1Hex, @k2Hex, @sp, @sponsorHex,
                             @quorum, @age, @spread, @minP, @maxP, @tb, @tms,
                             @payload, @sig, ret) = {
  new hashCh, vCh, nowCh in {
    hash!(payload.toUtf8Bytes(), *hashCh) |
    for (@digest <- hashCh) {
      verify!(digest, sig, sp, *vCh) |
      for (@ok <- vCh) {
        if (ok) {
          oracleNowV2!(*nowCh) |
          for (@now <- nowCh) {
            for (@s <<- oracleState) {
              match s.get("allowlist") {
                Nil => ret!((false, "no allowlist"))
                allowlist => {
                  new a0, a1, a2 in {
                    oracleInList!(allowlist, 0, k0, *a0) |
                    oracleInList!(allowlist, 0, k1, *a1) |
                    oracleInList!(allowlist, 0, k2, *a2) |
                    for (@in0 <- a0; @in1 <- a1; @in2 <- a2) {
                      if (in0 && in1 && in2) {
                        match s.get("feeds") {
                          Nil => ret!((false, "no feeds"))
                          feeds => {
                            match feeds.get(currency) {
                              Nil => {
                                new phCh in {
                                  oraclePolicyHashV2!(quorum, age, spread, minP, maxP, tb, tms, *phCh) |
                                  for (@policyHash <- phCh) {
                                    match s.get("keyUse") {
                                      Nil => ret!((false, "no key use"))
                                      keyUse => {
                                        new fCh in {
                                          fCh!({
                                            "reporters": [k0, k1, k2],
                                            "reporterHexes": [k0Hex, k1Hex, k2Hex],
                                            "sponsor": sp,
                                            "sponsorHex": sponsorHex,
                                            "quorum": quorum,
                                            "maxAgeBlocks": age,
                                            "maxSpreadBps": spread,
                                            "minPrice": minP,
                                            "maxPrice": maxP,
                                            "policyHash": policyHash,
                                            "trialStart": now,
                                            "trialBlocks": tb,
                                            "trialMinSubmits": tms,
                                            "seen0": false,
                                            "seen1": false,
                                            "seen2": false,
                                            "trialSubmits": 0,
                                            "active": false,
                                            "paused": false,
                                            "listedAt": 0
                                          }) |
                                          for (@feed <- fCh) {
                                            new u0, u1, u2 in {
                                              oracleKeyUseBump!(keyUse, k0Hex, 1, *u0) |
                                              for (@ku0 <- u0) {
                                                oracleKeyUseBump!(ku0, k1Hex, 1, *u1) |
                                                for (@ku1 <- u1) {
                                                  oracleKeyUseBump!(ku1, k2Hex, 1, *u2) |
                                                  for (@ku <- u2) {
                                                    oracleState!(s.set("feeds", feeds.set(currency, feed))
                                                                  .set("keyUse", ku)) |
                                                    ret!((true, Nil))
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
                              _ => ret!((false, "feed exists"))
                            }
                          }
                        }
                      } else { ret!((false, "reporter not allowed")) }
                    }
                  }
                }
              }
            }
          }
        } else { ret!((false, "bad sponsor signature")) }
      }
    }
  }
} |

// Increment three key-use counters (hex keys are derived later from the stored pubkeys;
// this helper is called only by openFeed with the raw keys, so the counters use a stable
// hex-free key: the ByteArray itself is not a Map key, so the bootstrap/setFeed path uses
// hex strings instead. Kept for the openFeed path where the allowlist is already hex.)
contract oracleKeyUseBump(@keyUse, @hex, @delta, ret) = {
  match keyUse.get(hex) {
    Nil => ret!(keyUse.set(hex, delta))
    n => ret!(keyUse.set(hex, n + delta))
  }
} |

contract OracleHubV2(@"activateFeed", @currency, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <<- oracleState) {
        match s.get("feeds") {
          Nil => ret!((false, "no feeds"))
          feeds => {
            match feeds.get(currency) {
              Nil => ret!((false, "no feed"))
              feed => {
                if (feed.get("active")) { ret!((false, "already active")) }
                else {
                  if (feed.get("paused")) { ret!((false, "paused")) }
                  else {
                    if (now < feed.get("trialStart") + feed.get("trialBlocks")) {
                      ret!((false, "trial not elapsed"))
                    } else {
                      if (feed.get("trialSubmits") < feed.get("trialMinSubmits")) {
                        ret!((false, "trial submits"))
                      } else {
                        new seenCh in {
                          oracleCountSeen!(feed, *seenCh) |
                          for (@seen <- seenCh) {
                            if (seen < feed.get("quorum")) { ret!((false, "trial reporters")) }
                            else { oracleActivateCheck!(currency, feed, now, s, feeds, *ret) }
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

contract oracleActivateCheck(@currency, @feed, @now, @s, @feeds, ret) = {
  new e0, e1, e2, v0, v1, v2, f0, f1, f2 in {
    oracleEntryOf!(currency, 0, *e0) |
    oracleEntryOf!(currency, 1, *e1) |
    oracleEntryOf!(currency, 2, *e2) |
    for (@x0 <- e0; @x1 <- e1; @x2 <- e2) {
      oracleValueV2!(x0, *v0) |
      oracleValueV2!(x1, *v1) |
      oracleValueV2!(x2, *v2) |
      for (@(p0, h0) <- v0; @(p1, h1) <- v1; @(p2, h2) <- v2) {
        oracleIsFreshV2!(p0, h0, now, feed.get("maxAgeBlocks"), feed.get("minPrice"), feed.get("maxPrice"), *f0) |
        oracleIsFreshV2!(p1, h1, now, feed.get("maxAgeBlocks"), feed.get("minPrice"), feed.get("maxPrice"), *f1) |
        oracleIsFreshV2!(p2, h2, now, feed.get("maxAgeBlocks"), feed.get("minPrice"), feed.get("maxPrice"), *f2) |
        for (@q0 <- f0; @q1 <- f1; @q2 <- f2) {
          new i0, i1, i2, mCh, mhCh, mxCh, mnCh in {
            oracleB2IV2!(q0, *i0) | oracleB2IV2!(q1, *i1) | oracleB2IV2!(q2, *i2) |
            oracleMedian3V2!(p0, p1, p2, *mCh) |
            oracleMax3V2!(h0, h1, h2, *mhCh) |
            oracleMax3V2!(p0, p1, p2, *mxCh) |
            oracleMin3V2!(p0, p1, p2, *mnCh) |
            for (@i0v <- i0; @i1v <- i1; @i2v <- i2; @median <- mCh; @maxH <- mhCh;
                 @pMax <- mxCh; @pMin <- mnCh) {
              new okCh in {
                oracleDecideV2!(i0v + i1v + i2v, feed.get("quorum"), pMax - pMin,
                                median, feed.get("maxSpreadBps"),
                                feed.get("minPrice"), feed.get("maxPrice"), *okCh) |
                for (@ok <- okCh) {
                  if (ok) {
                    for (@cur <- oracleState) {
                      match cur.get("feeds") {
                        Nil => ret!((false, "no feeds"))
                        curFeeds => {
                          match curFeeds.get(currency) {
                            Nil => ret!((false, "no feed"))
                            f => {
                              oracleState!(cur.set("feeds", curFeeds.set(currency,
                                f.set("active", true).set("listedAt", now)))) |
                              ret!((true, Nil))
                            }
                          }
                        }
                      }
                    }
                  } else { ret!((false, "quorum/spread/band")) }
                }
              }
            }
          }
        }
      }
    }
  }
} |

contract OracleHubV2(@"submit", @currency, @price, @height, @index, @pubKey, @sig, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <<- oracleState) {
        match s.get("feeds") {
          Nil => ret!((false, "no feeds"))
          feeds => {
            match feeds.get(currency) {
              Nil => ret!((false, "no feed"))
              feed => {
                if (feed.get("paused")) { ret!((false, "feed paused")) }
                else {
                  if (index < 0 || index >= 3) { ret!((false, "bad index")) }
                  else {
                    match feed.get("reporters") {
                      reporters => {
                        match reporters.nth(index) {
                          allowed => {
                        if (allowed == pubKey) {
                          if (height > now) { ret!((false, "future height")) }
                          else {
                            if ((now - height) > 1000) { ret!((false, "stale height")) }
                            else {
                              new hashCh, vCh in {
                                match ("rcash:oracle:v1|/root|" ++ currency ++ "|"
                                       ++ price.toString() ++ "|" ++ height.toString()) {
                                  payload => {
                                    hash!(payload.toUtf8Bytes(), *hashCh) |
                                    for (@digest <- hashCh) {
                                      verify!(digest, sig, pubKey, *vCh) |
                                      for (@ok <- vCh) {
                                        if (ok) { oracleStoreV2!(currency, index, price, height, *ret) }
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
      }
    }
  }
  }
} |

contract OracleHubV2(@"get", @currency, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      new feedCh, e0, e1, e2 in {
        oracleFeedOf!(currency, *feedCh) |
        for (@feed <- feedCh) {
          match feed {
            Nil => ret!((false, "no feed"))
            f => {
              if (f.get("active") == false) {
                ret!((true, {"price": 0, "height": 0, "fresh": false,
                              "reason": "trial", "active": false, "paused": f.get("paused")}))
              } else {
                if (f.get("paused")) {
                  ret!((true, {"price": 0, "height": 0, "fresh": false,
                                "reason": "paused", "active": true, "paused": true}))
                } else {
                  oracleEntryOf!(currency, 0, *e0) |
                  oracleEntryOf!(currency, 1, *e1) |
                  oracleEntryOf!(currency, 2, *e2) |
                  for (@x0 <- e0; @x1 <- e1; @x2 <- e2) {
                    new v0, v1, v2 in {
                      oracleValueV2!(x0, *v0) |
                      oracleValueV2!(x1, *v1) |
                      oracleValueV2!(x2, *v2) |
                      for (@(p0, h0) <- v0; @(p1, h1) <- v1; @(p2, h2) <- v2) {
                        new f0, f1, f2 in {
                          oracleIsFreshV2!(p0, h0, now, f.get("maxAgeBlocks"), f.get("minPrice"), f.get("maxPrice"), *f0) |
                          oracleIsFreshV2!(p1, h1, now, f.get("maxAgeBlocks"), f.get("minPrice"), f.get("maxPrice"), *f1) |
                          oracleIsFreshV2!(p2, h2, now, f.get("maxAgeBlocks"), f.get("minPrice"), f.get("maxPrice"), *f2) |
                          for (@q0 <- f0; @q1 <- f1; @q2 <- f2) {
                            new i0, i1, i2, mCh, mhCh, mxCh, mnCh in {
                              oracleB2IV2!(q0, *i0) | oracleB2IV2!(q1, *i1) | oracleB2IV2!(q2, *i2) |
                              oracleMedian3V2!(p0, p1, p2, *mCh) |
                              oracleMax3V2!(h0, h1, h2, *mhCh) |
                              oracleMax3V2!(p0, p1, p2, *mxCh) |
                              oracleMin3V2!(p0, p1, p2, *mnCh) |
                              for (@i0v <- i0; @i1v <- i1; @i2v <- i2; @median <- mCh;
                                   @maxH <- mhCh; @pMax <- mxCh; @pMin <- mnCh) {
                                new okCh in {
                                  oracleDecideV2!(i0v + i1v + i2v, f.get("quorum"), pMax - pMin,
                                                  median, f.get("maxSpreadBps"),
                                                  f.get("minPrice"), f.get("maxPrice"), *okCh) |
                                  for (@ok <- okCh) {
                                    if (ok) {
                                      ret!((true, {"price": median, "height": maxH,
                                                    "fresh": true, "reason": "ok",
                                                    "active": true, "paused": false}))
                                    } else {
                                      ret!((true, {"price": median, "height": maxH,
                                                    "fresh": false, "reason": "quorum/spread/band",
                                                    "active": true, "paused": false}))
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

contract oraclePairReplyV2(@fb, @fq, @pbase, @pquote, ret) = {
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

contract OracleHubV2(@"getPair", @base, @quote, ret) = {
  new bCh, qCh in {
    OracleHubV2!("get", base, *bCh) |
    OracleHubV2!("get", quote, *qCh) |
    for (@rb <- bCh; @rq <- qCh) {
      match rb {
        (true, pb) => {
          match rq {
            (true, pq) => {
              oraclePairReplyV2!(pb.get("fresh"), pq.get("fresh"),
                                 pb.get("price"), pq.get("price"), *ret)
            }
            _ => ret!((false, "quote feed error"))
          }
        }
        _ => ret!((false, "base feed error"))
      }
    }
  }
} |

contract OracleHubV2(@"feedStatus", @currency, ret) = {
  new feedCh in {
    oracleFeedOf!(currency, *feedCh) |
    for (@feed <- feedCh) {
      match feed {
        Nil => ret!((false, "no feed"))
        f => ret!((true, f))
      }
    }
  }
} |

contract OracleHubV2(@"feeds", ret) = {
  for (@s <<- oracleState) {
    match s.get("feeds") {
      Nil => ret!((true, {}))
      feeds => ret!((true, feeds))
    }
  }
} |

contract OracleHubV2(@"reporters", ret) = {
  for (@s <<- oracleState) {
    match s.get("allowlist") {
      Nil => ret!((false, "no reporters"))
      allowlist => ret!((true, allowlist))
    }
  }
} |

// ---- Admin: allowlist growth, feed rotation/policy, pause --------------------------------

contract oracleAdminApplyV2(@action, @args, @nonce, ret) = {
  for (@s <- oracleState) {
    if (nonce <= s.get("govNonce")) {
      oracleState!(s) | ret!((false, "replay"))
    } else {
      if (action == "addReporter") {
        match args.nth(0) {
          hex => {
            match hex.hexToBytes() {
              key => {
                match s.get("allowlist") {
                  Nil => { oracleState!(s) | ret!((false, "no allowlist")) }
                  allowlist => {
                    new inCh in {
                      oracleInList!(allowlist, 0, key, *inCh) |
                      for (@present <- inCh) {
                        if (present) { oracleState!(s) | ret!((false, "reporter exists")) }
                        else {
                          if (allowlist.length() >= 32) { oracleState!(s) | ret!((false, "allowlist full")) }
                          else {
                            oracleState!(s.set("allowlist", allowlist ++ [key]).set("govNonce", nonce)) |
                            ret!((true, Nil))
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
        if (action == "removeReporter") {
          match args.nth(0) {
            hex => {
              match hex.hexToBytes() {
                key => {
                  match s.get("keyUse") {
                    Nil => { oracleState!(s) | ret!((false, "no key use")) }
                    keyUse => {
                      match keyUse.get(hex) {
                        Nil => {
                          match s.get("allowlist") {
                            Nil => { oracleState!(s) | ret!((false, "no allowlist")) }
                            allowlist => {
                              new outChNil in {
                                oracleListRemove!(allowlist, 0, key, [], *outChNil) |
                                for (@nextNil <- outChNil) {
                                  oracleState!(s.set("allowlist", nextNil).set("govNonce", nonce)) |
                                  ret!((true, Nil))
                                }
                              }
                            }
                          }
                        }
                        used => {
                          if (used > 0) { oracleState!(s) | ret!((false, "reporter in use")) }
                          else {
                            match s.get("allowlist") {
                              Nil => { oracleState!(s) | ret!((false, "no allowlist")) }
                              allowlist => {
                                new outCh in {
                                  oracleListRemove!(allowlist, 0, key, [], *outCh) |
                                  for (@next <- outCh) {
                                    oracleState!(s.set("allowlist", next).set("govNonce", nonce)) |
                                    ret!((true, Nil))
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
          if (action == "pauseFeed") {
            match args.nth(0) {
              currency => {
                match args.nth(1) {
                  p => {
                    match s.get("feeds") {
                      Nil => { oracleState!(s) | ret!((false, "no feeds")) }
                      feeds => {
                        match feeds.get(currency) {
                          Nil => { oracleState!(s) | ret!((false, "no feed")) }
                          feed => {
                            oracleState!(s.set("feeds", feeds.set(currency, feed.set("paused", p == 1)))
                                          .set("govNonce", nonce)) |
                            ret!((true, Nil))
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          } else {
            if (action == "restartTrial") {
              match args.nth(0) {
                currency => {
                  match s.get("feeds") {
                    Nil => { oracleState!(s) | ret!((false, "no feeds")) }
                    feeds => {
                      match feeds.get(currency) {
                        Nil => { oracleState!(s) | ret!((false, "no feed")) }
                        feed => {
                          oracleState!(s.set("feeds", feeds.set(currency,
                            feed.set("active", false).set("seen0", false).set("seen1", false)
                              .set("seen2", false).set("trialSubmits", 0)))
                            .set("govNonce", nonce)) |
                          ret!((true, Nil))
                        }
                      }
                    }
                  }
                }
              }
            } else {
              if (action == "removeFeed") {
                match args.nth(0) {
                  currency => {
                    match s.get("feeds") {
                      Nil => { oracleState!(s) | ret!((false, "no feeds")) }
                      feeds => {
                        match feeds.get(currency) {
                          Nil => { oracleState!(s) | ret!((false, "no feed")) }
                          feed => {
                            oracleState!(s.set("feeds", feeds.set(currency,
                              feed.set("active", false).set("paused", true)))
                              .set("govNonce", nonce)) |
                            ret!((true, Nil))
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
      }
    }
  }
} |

contract OracleHubV2(@"admin", @nonce, @action, @args, @sigs, ret) = {
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
                      if (ok) { oracleAdminApplyV2!(action, args, nonce, *ret) }
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
