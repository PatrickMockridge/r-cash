// OracleHub v0.2: a global reporter allowlist and one feed state per currency.
//
// Hub state: {allowlist: [pubKeyBytes], keyUse: Map(hex -> Int),
//             feeds: Map(currency -> {"feed": *oracleFeed, "state": *feedState}),
//             admins, threshold, govNonce}
// Feed state: {currency, reporters:[k0,k1,k2], sponsor, sponsorHex, quorum,
//              maxAgeBlocks, maxSpreadBps, minPrice, maxPrice, policyHash,
//              trialStart, trialBlocks, trialMinSubmits, seen0/1/2, trialSubmits,
//              active, paused, listedAt, prices: Map(index -> {price,height})}
//
// `oracleFeed` is one stateless contract; each feed has its own state cell. The hub
// routes calls to the feed and state. No shared price/feed map, so submits and reads
// cannot contend on one cell.

contract oracleNowV2(ret) = {
  new ch in { bd!(*ch) | for (@h, @s, @t <- ch) { ret!(h) } }
} |

contract oracleB2IV2(@b, ret) = { if (b) { ret!(1) } else { ret!(0) } } |

contract oracleInList(@items, @i, @key, ret) = {
  if (i >= items.length()) { ret!(false) }
  else { match items.nth(i) { x => { if (x == key) { ret!(true) } else { oracleInList!(items, i + 1, key, *ret) } } } }
} |

contract oracleListRemove(@items, @i, @key, @acc, ret) = {
  if (i >= items.length()) { ret!(acc) }
  else {
    match items.nth(i) {
      x => { if (x == key) { oracleListRemove!(items, i + 1, key, acc, *ret) } else { oracleListRemove!(items, i + 1, key, acc ++ [x], *ret) } }
    }
  }
} |

contract oracleMedian3V2(@a, @b, @c, ret) = {
  if (a < b) { if (b < c) { ret!(b) } else { if (a < c) { ret!(c) } else { ret!(a) } } }
  else { if (a < c) { ret!(a) } else { if (b < c) { ret!(c) } else { ret!(b) } } }
} |

contract oracleMax3V2(@a, @b, @c, ret) = {
  if (a >= b) { if (a >= c) { ret!(a) } else { ret!(c) } }
  else { if (b >= c) { ret!(b) } else { ret!(c) } }
} |

contract oracleMin3V2(@a, @b, @c, ret) = {
  if (a <= b) { if (a <= c) { ret!(a) } else { ret!(c) } }
  else { if (b <= c) { ret!(b) } else { ret!(c) } }
} |

contract oracleIsFreshV2(@price, @height, @now, @maxAge, @minP, @maxP, ret) = {
  if (height <= 0) { ret!(false) }
  else {
    if (height > now) { ret!(false) }
    else {
      if ((now - height) > maxAge) { ret!(false) }
      else { if (price < minP) { ret!(false) } else { if (price > maxP) { ret!(false) } else { ret!(true) } } }
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
        else { if ((spread * 10000) > (median * spreadBps)) { ret!(false) } else { ret!(true) } }
      }
    }
  }
} |

contract oraclePolicyHashV2(@quorum, @age, @spread, @minP, @maxP, @tb, @tms, ret) = {
  termsHash!(*hash, "rcash:oracle-policy:v1", [quorum, age, spread, minP, maxP, tb, tms], *ret)
} |

contract oracleFeedPayload(@currency, @k0, @k1, @k2, @sponsor, @quorum, @age, @spread,
                           @minP, @maxP, @tb, @tms, ret) = {
  ret!("rcash:oracle-feed:v1|/root|" ++ currency ++ "|" ++ k0 ++ "|" ++ k1 ++ "|" ++ k2
       ++ "|" ++ sponsor ++ "|" ++ quorum.toString() ++ "|" ++ age.toString()
       ++ "|" ++ spread.toString() ++ "|" ++ minP.toString() ++ "|" ++ maxP.toString()
       ++ "|" ++ tb.toString() ++ "|" ++ tms.toString())
} |

contract oracleMarkSeen(@feed, @index, ret) = {
  if (index == 0) { ret!(feed.set("seen0", true)) }
  else { if (index == 1) { ret!(feed.set("seen1", true)) } else { ret!(feed.set("seen2", true)) } }
} |

contract oracleCountSeen(@feed, ret) = {
  new c0, c1, c2 in {
    oracleB2IV2!(feed.get("seen0"), *c0) |
    oracleB2IV2!(feed.get("seen1"), *c1) |
    oracleB2IV2!(feed.get("seen2"), *c2) |
    for (@a <- c0; @b <- c1; @c <- c2) { ret!(a + b + c) }
  }
} |

contract oracleValuePair(@entry, ret) = {
  match entry {
    Nil => ret!((0, 0))
    e => { match e.get("price") { p => { match e.get("height") { h => ret!((p, h)) } } } }
  }
} |

// Write a price using the state snapshot the submit consumed.
contract oracleFeedStore(stateCh, @s, @index, @price, @height, ret) = {
  match s.get("prices") {
    Nil => { stateCh!(s) | ret!((false, "no prices")) }
    prices => {
      match prices.get(index) {
        Nil => {
          new seenCh in {
            oracleMarkSeen!(s, index, *seenCh) |
            for (@f1 <- seenCh) {
              match f1.get("trialSubmits") {
                n => { match f1.set("trialSubmits", n + 1) { f2 => {
                  stateCh!(f2.set("prices", prices.set(index, {"price": price, "height": height}))) |
                  ret!((true, Nil))
                } } }
              }
            }
          }
        }
        old => {
          match old.get("height") {
            oldH => {
              if (height > oldH) {
                new seenCh2 in {
                  oracleMarkSeen!(s, index, *seenCh2) |
                  for (@f1 <- seenCh2) {
                    match f1.get("trialSubmits") {
                      n2 => { match f1.set("trialSubmits", n2 + 1) { f2 => {
                        stateCh!(f2.set("prices", prices.set(index, {"price": price, "height": height}))) |
                        ret!((true, Nil))
                      } } }
                    }
                  }
                }
              } else { stateCh!(s) | ret!((false, "height not monotonic")) }
            }
          }
        }
      }
    }
  }
} |

// Decide freshness for a feed's active prices.
contract oracleFeedRead(@s, @now, ret) = {
  match s.get("prices") {
    Nil => ret!((false, "no prices"))
    prices => {
      new e0, e1, e2 in {
        match prices.get(0) {
          Nil => e0!(Nil)
          x => e0!(x)
        } |
        match prices.get(1) {
          Nil => e1!(Nil)
          x => e1!(x)
        } |
        match prices.get(2) {
          Nil => e2!(Nil)
          x => e2!(x)
        } |
        for (@x0 <- e0; @x1 <- e1; @x2 <- e2) {
          new v0, v1, v2 in {
            oracleValuePair!(x0, *v0) | oracleValuePair!(x1, *v1) | oracleValuePair!(x2, *v2) |
            for (@(p0,h0) <- v0; @(p1,h1) <- v1; @(p2,h2) <- v2) {
              new f0, f1, f2 in {
                oracleIsFreshV2!(p0,h0,now,s.get("maxAgeBlocks"),s.get("minPrice"),s.get("maxPrice"),*f0) |
                oracleIsFreshV2!(p1,h1,now,s.get("maxAgeBlocks"),s.get("minPrice"),s.get("maxPrice"),*f1) |
                oracleIsFreshV2!(p2,h2,now,s.get("maxAgeBlocks"),s.get("minPrice"),s.get("maxPrice"),*f2) |
                for (@q0 <- f0; @q1 <- f1; @q2 <- f2) {
                  new i0,i1,i2,mCh,mhCh,mxCh,mnCh in {
                    oracleB2IV2!(q0,*i0) | oracleB2IV2!(q1,*i1) | oracleB2IV2!(q2,*i2) |
                    oracleMedian3V2!(p0,p1,p2,*mCh) |
                    oracleMax3V2!(h0,h1,h2,*mhCh) |
                    oracleMax3V2!(p0,p1,p2,*mxCh) |
                    oracleMin3V2!(p0,p1,p2,*mnCh) |
                    for (@i0v <- i0; @i1v <- i1; @i2v <- i2; @median <- mCh; @maxH <- mhCh; @pMax <- mxCh; @pMin <- mnCh) {
                      new okCh in {
                        oracleDecideV2!(i0v+i1v+i2v, s.get("quorum"), pMax-pMin, median,
                                        s.get("maxSpreadBps"), s.get("minPrice"), s.get("maxPrice"), *okCh) |
                        for (@ok <- okCh) {
                          if (ok) {
                            ret!((true, {"price": median, "height": maxH, "fresh": true,
                                         "reason": "ok", "active": true, "paused": false}))
                          } else {
                            ret!((true, {"price": median, "height": maxH, "fresh": false,
                                         "reason": "quorum/spread/band", "active": true, "paused": false}))
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

contract oracleFeedActivateCheck(stateCh, @s, @now, ret) = {
  new readCh in {
    oracleFeedRead!(s, now, *readCh) |
    for (@r <- readCh) {
      match r {
        (true, feed) => {
          if (feed.get("fresh")) {
            stateCh!(s.set("active", true).set("listedAt", now)) |
            ret!((true, Nil))
          } else { stateCh!(s) | ret!((false, "quorum/spread/band")) }
        }
        _ => { stateCh!(s) | ret!((false, "read")) }
      }
    }
  }
} |

// ---- The stateless feed contract ---------------------------------------------------------

contract oracleFeed(@"submit", stateCh, @price, @height, @index, @pubKey, @sig, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <- stateCh) {
        if (s.get("paused")) { stateCh!(s) | ret!((false, "paused")) }
        else {
          if (index < 0 || index >= 3) { stateCh!(s) | ret!((false, "bad index")) }
          else {
            match s.get("reporters") {
              reporters => {
                match reporters.nth(index) {
                  allowed => {
                    if (allowed == pubKey) {
                      if (height > now) { stateCh!(s) | ret!((false, "future height")) }
                      else {
                        if ((now - height) > 1000) { stateCh!(s) | ret!((false, "stale height")) }
                        else {
                          new hCh, vCh in {
                            match ("rcash:oracle:v1|/root|" ++ s.get("currency") ++ "|"
                                   ++ price.toString() ++ "|" ++ height.toString()) {
                              payload => {
                                hash!(payload.toUtf8Bytes(), *hCh) |
                                for (@digest <- hCh) {
                                  verify!(digest, sig, pubKey, *vCh) |
                                  for (@ok <- vCh) {
                                    if (ok) { oracleFeedStore!(*stateCh, s, index, price, height, *ret) }
                                    else { stateCh!(s) | ret!((false, "bad signature")) }
                                  }
                                }
                              }
                            }
                          }
                        }
                      }
                    } else { stateCh!(s) | ret!((false, "not the reporter at that index")) }
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

contract oracleFeed(@"get", stateCh, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <<- stateCh) {
        if (s.get("active") == false) {
          ret!((true, {"price": 0, "height": 0, "fresh": false, "reason": "trial",
                       "active": false, "paused": s.get("paused")}))
        } else {
          if (s.get("paused")) {
            ret!((true, {"price": 0, "height": 0, "fresh": false, "reason": "paused",
                         "active": true, "paused": true}))
          } else { oracleFeedRead!(s, now, *ret) }
        }
      }
    }
  }
} |

contract oracleFeed(@"feedStatus", stateCh, ret) = {
  for (@s <<- stateCh) {
    ret!((true, {
      "currency": s.get("currency"), "reporters": s.get("reporters"),
      "reporterHexes": s.get("reporterHexes"), "sponsor": s.get("sponsor"),
      "sponsorHex": s.get("sponsorHex"), "quorum": s.get("quorum"),
      "maxAgeBlocks": s.get("maxAgeBlocks"), "maxSpreadBps": s.get("maxSpreadBps"),
      "minPrice": s.get("minPrice"), "maxPrice": s.get("maxPrice"),
      "policyHash": s.get("policyHash"), "trialStart": s.get("trialStart"),
      "trialBlocks": s.get("trialBlocks"), "trialMinSubmits": s.get("trialMinSubmits"),
      "seen0": s.get("seen0"), "seen1": s.get("seen1"), "seen2": s.get("seen2"),
      "trialSubmits": s.get("trialSubmits"), "active": s.get("active"),
      "paused": s.get("paused"), "listedAt": s.get("listedAt")
    }))
  }
} |

contract oracleFeed(@"activate", stateCh, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <- stateCh) {
        if (s.get("active")) { stateCh!(s) | ret!((false, "already active")) }
        else {
          if (s.get("paused")) { stateCh!(s) | ret!((false, "paused")) }
          else {
            if (now < s.get("trialStart") + s.get("trialBlocks")) {
              stateCh!(s) | ret!((false, "trial not elapsed"))
            } else {
              if (s.get("trialSubmits") < s.get("trialMinSubmits")) {
                stateCh!(s) | ret!((false, "trial submits"))
              } else {
                new seenCh in {
                  oracleCountSeen!(s, *seenCh) |
                  for (@seen <- seenCh) {
                    if (seen < s.get("quorum")) { stateCh!(s) | ret!((false, "trial reporters")) }
                    else { oracleFeedActivateCheck!(*stateCh, s, now, *ret) }
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

contract oracleFeed(@"setPaused", stateCh, @p, ret) = {
  for (@s <- stateCh) { stateCh!(s.set("paused", p == 1)) | ret!((true, Nil)) }
} |

contract oracleFeed(@"restartTrial", stateCh, ret) = {
  new nowCh in {
    oracleNowV2!(*nowCh) |
    for (@now <- nowCh) {
      for (@s <- stateCh) {
        stateCh!(s.set("active", false).set("seen0", false).set("seen1", false)
                  .set("seen2", false).set("trialSubmits", 0).set("trialStart", now)) |
        ret!((true, Nil))
      }
    }
  }
} |

// ---- Hub ---------------------------------------------------------------------------------

contract oracleFeedEntry(@currency, ret) = {
  for (@s <<- oracleState) {
    match s.get("feeds") {
      Nil => ret!(Nil)
      feeds => { match feeds.get(currency) { Nil => ret!(Nil) entry => ret!(entry) } }
    }
  }
} |

contract OracleHubV2(@"openFeed", @currency, @k0Hex, @k1Hex, @k2Hex, @sponsorHex, @sig,
                      @quorum, @age, @spread, @minP, @maxP, @tb, @tms, ret) = {
  new k0Ch, k1Ch, k2Ch, spCh, payloadCh, hashCh, vCh, nowCh, feed, feedState in {
    match k0Hex.hexToBytes() { k0 => k0Ch!(k0) } |
    match k1Hex.hexToBytes() { k1 => k1Ch!(k1) } |
    match k2Hex.hexToBytes() { k2 => k2Ch!(k2) } |
    match sponsorHex.hexToBytes() { sp => spCh!(sp) } |
    oracleFeedPayload!(currency, k0Hex, k1Hex, k2Hex, sponsorHex, quorum, age, spread,
                       minP, maxP, tb, tms, *payloadCh) |
    for (@k0 <- k0Ch; @k1 <- k1Ch; @k2 <- k2Ch; @sp <- spCh; @payload <- payloadCh) {
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
                  if ((k0Hex == sponsorHex && k1Hex == sponsorHex)
                      || (k0Hex == sponsorHex && k2Hex == sponsorHex)
                      || (k1Hex == sponsorHex && k2Hex == sponsorHex)) {
                    ret!((false, "sponsor conflict"))
                  } else {
                    hash!(payload.toUtf8Bytes(), *hashCh) |
                    for (@digest <- hashCh) {
                      verify!(digest, sig, sp, *vCh) |
                      for (@ok <- vCh) {
                        if (ok == false) { ret!((false, "bad sponsor signature")) }
                        else {
                          oracleNowV2!(*nowCh) |
                          for (@now <- nowCh) {
                            for (@s <- oracleState) {
                              match s.get("allowlist") {
                                Nil => { oracleState!(s) | ret!((false, "no allowlist")) }
                                allowlist => {
                                  new a0, a1, a2 in {
                                    oracleInList!(allowlist, 0, k0, *a0) |
                                    oracleInList!(allowlist, 0, k1, *a1) |
                                    oracleInList!(allowlist, 0, k2, *a2) |
                                    for (@in0 <- a0; @in1 <- a1; @in2 <- a2) {
                                      if (in0 && in1 && in2) {
                                        match s.get("feeds") {
                                          Nil => { oracleState!(s) | ret!((false, "no feeds")) }
                                          feeds => {
                                            match feeds.get(currency) {
                                              Nil => {
                                                new phCh in {
                                                  oraclePolicyHashV2!(quorum, age, spread, minP, maxP, tb, tms, *phCh) |
                                                  for (@policyHash <- phCh) {
                                                    feedState!({
                                                      "currency": currency,
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
                                                      "listedAt": 0,
                                                      "prices": {}
                                                    }) |
                                                    contract feed(@"submit", @price2, @height2, @index2, @pubKey2, @sig2, retF) = {
                                                      oracleFeed!("submit", *feedState, price2, height2, index2, pubKey2, sig2, *retF)
                                                    } |
                                                    contract feed(@"get", retF) = {
                                                      oracleFeed!("get", *feedState, *retF)
                                                    } |
                                                    contract feed(@"feedStatus", retF) = {
                                                      oracleFeed!("feedStatus", *feedState, *retF)
                                                    } |
                                                    contract feed(@"activate", retF) = {
                                                      oracleFeed!("activate", *feedState, *retF)
                                                    } |
                                                    contract feed(@"setPaused", @p2, retF) = {
                                                      oracleFeed!("setPaused", *feedState, p2, *retF)
                                                    } |
                                                    contract feed(@"restartTrial", retF) = {
                                                      oracleFeed!("restartTrial", *feedState, *retF)
                                                    } |
                                                    oracleState!(s.set("feeds", feeds.set(currency, *feed))) |
                                                    ret!((true, Nil))
                                                  }
                                                }
                                              }
                                              _ => { oracleState!(s) | ret!((false, "feed exists")) }
                                            }
                                          }
                                        }
                                      } else { oracleState!(s) | ret!((false, "reporter not allowed")) }
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

contract OracleHubV2(@"submit", @currency, @price, @height, @index, @pubKey, @sig, ret) = {
  new entryCh in {
    oracleFeedEntry!(currency, *entryCh) |
    for (@entry <- entryCh) {
      match entry {
        Nil => ret!((false, "no feed"))
        feedCap => { @feedCap!("submit", price, height, index, pubKey, sig, *ret) }
      }
    }
  }
} |

contract OracleHubV2(@"get", @currency, ret) = {
  new entryCh in {
    oracleFeedEntry!(currency, *entryCh) |
    for (@entry <- entryCh) {
      match entry {
        Nil => ret!((false, "no feed"))
        feedCap => { @feedCap!("get", *ret) }
      }
    }
  }
} |

contract OracleHubV2(@"feedStatus", @currency, ret) = {
  new entryCh in {
    oracleFeedEntry!(currency, *entryCh) |
    for (@entry <- entryCh) {
      match entry {
        Nil => ret!((false, "no feed"))
        feedCap => { @feedCap!("feedStatus", *ret) }
      }
    }
  }
} |

contract OracleHubV2(@"activateFeed", @currency, ret) = {
  new entryCh in {
    oracleFeedEntry!(currency, *entryCh) |
    for (@entry <- entryCh) {
      match entry {
        Nil => ret!((false, "no feed"))
        feedCap => { @feedCap!("activate", *ret) }
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
            (true, pq) => { oraclePairReplyV2!(pb.get("fresh"), pq.get("fresh"), pb.get("price"), pq.get("price"), *ret) }
            _ => ret!((false, "quote feed error"))
          }
        }
        _ => ret!((false, "base feed error"))
      }
    }
  }
} |

contract OracleHubV2(@"reporters", ret) = {
  for (@s <<- oracleState) {
    match s.get("allowlist") { Nil => ret!((false, "no reporters")) a => ret!((true, a)) }
  }
} |

contract oracleAddReporter(@s, @args, @nonce, ret) = {
  match args.nth(0) {
    hex => {
      match hex.hexToBytes() {
        key => {
          match s.get("allowlist") {
            Nil => ret!((s, (false, "no allowlist")))
            allowlist => {
              new inCh in {
                oracleInList!(allowlist, 0, key, *inCh) |
                for (@present <- inCh) {
                  if (present) { ret!((s, (false, "reporter exists"))) }
                  else {
                    if (allowlist.length() >= 32) { ret!((s, (false, "allowlist full"))) }
                    else { ret!((s.set("allowlist", allowlist ++ [key]).set("govNonce", nonce), (true, Nil))) }
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

contract oracleRemoveReporter(@s, @args, @nonce, ret) = {
  match args.nth(0) {
    hex => {
      match hex.hexToBytes() {
        key => {
          match s.get("allowlist") {
            Nil => ret!((s, (false, "no allowlist")))
            allowlist => {
              new outCh in {
                oracleListRemove!(allowlist, 0, key, [], *outCh) |
                for (@next <- outCh) {
                  ret!((s.set("allowlist", next).set("govNonce", nonce), (true, Nil)))
                }
              }
            }
          }
        }
      }
    }
  }
} |

contract oraclePauseFeedAdmin(@s, @args, @nonce, ret) = {
  match args.nth(0) {
    currency => {
      match args.nth(1) {
        p => {
          match s.get("feeds") {
            Nil => ret!((s, (false, "no feeds")))
            feeds => {
              match feeds.get(currency) {
                Nil => ret!((s, (false, "no feed")))
                feedCap => {
                  new fCh in {
                    @feedCap!("setPaused", p, *fCh) |
                    for (@r <- fCh) { ret!((s.set("govNonce", nonce), r)) }
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

contract oracleRestartTrialAdmin(@s, @args, @nonce, ret) = {
  match args.nth(0) {
    currency => {
      match s.get("feeds") {
        Nil => ret!((s, (false, "no feeds")))
        feeds => {
          match feeds.get(currency) {
            Nil => ret!((s, (false, "no feed")))
            feedCap => {
              new fCh in {
                @feedCap!("restartTrial", *fCh) |
                for (@r <- fCh) { ret!((s.set("govNonce", nonce), r)) }
              }
            }
          }
        }
      }
    }
  }
} |

contract oracleAdminApplyV2(@action, @args, @nonce, ret) = {
  for (@s <- oracleState) {
    if (nonce <= s.get("govNonce")) {
      oracleState!(s) | ret!((false, "replay"))
    } else {
      if (action == "addReporter") {
        new ch in {
          oracleAddReporter!(s, args, nonce, *ch) |
          for (@(ns, r) <- ch) { oracleState!(ns) | ret!(r) }
        }
      } else {
        if (action == "removeReporter") {
          new ch in {
            oracleRemoveReporter!(s, args, nonce, *ch) |
            for (@(ns, r) <- ch) { oracleState!(ns) | ret!(r) }
          }
        } else {
          if (action == "pauseFeed") {
            new ch in {
              oraclePauseFeedAdmin!(s, args, nonce, *ch) |
              for (@(ns, r) <- ch) { oracleState!(ns) | ret!(r) }
            }
          } else {
            if (action == "restartTrial") {
              new ch in {
                oracleRestartTrialAdmin!(s, args, nonce, *ch) |
                for (@(ns, r) <- ch) { oracleState!(ns) | ret!(r) }
              }
            } else { oracleState!(s) | ret!((false, "unknown action")) }
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
