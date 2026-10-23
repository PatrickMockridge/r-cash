// LiquidityLock: the sponsor's initial LP shares, locked until a height.
//
// Captured: lockState, lpIssuer, lpBrand, lpPurse, deployerIdOps, bd, Guard helpers.
// State: {marketId, termsHash, beneficiaryPubKey, beneficiaryOwnerId, lpBrand, lpIssuer,
//         minShares, untilHeight, shares, funded, released, cancelled, fundedAt,
//         admins, threshold, govNonce}
// Release is beneficiary-only and time-locked. A 2-of-3 cancel is the fallback for a
// cancelled draft market; delisting an active market does not release the seed early.

contract lockNow(ret) = {
  new ch in { bd!(*ch) | for (@h, @s, @t <- ch) { ret!(h) } }
} |

contract LiquidityLock(@"lock", lpPayment, ret) = {
  new amtCh, nowCh in {
    @lpIssuer!("getAmountOf", *lpPayment, *amtCh) |
    lockNow!(*nowCh) |
    for (@a <- amtCh; @now <- nowCh) {
      match a {
        (true, shares) => {
          for (@s <<- lockState) {
            if (s.get("funded")) { ret!((false, "already funded")) }
            else {
              if (s.get("cancelled")) { ret!((false, "cancelled")) }
              else {
                if (shares < s.get("minShares")) { ret!((false, "below min shares")) }
                else {
                  if (now >= s.get("untilHeight")) { ret!((false, "lock expired")) }
                  else {
                    new depCh in {
                      @lpPurse!("deposit", *lpPayment, *depCh) |
                      for (@d <- depCh) {
                        match d {
                          (true, bal) => {
                            for (@cur <- lockState) {
                              if (cur.get("funded")) { lockState!(cur) | ret!((false, "already funded")) }
                              else {
                                lockState!(cur.set("shares", shares).set("funded", true)
                                              .set("fundedAt", now)) |
                                ret!((true, shares))
                              }
                            }
                          }
                          _ => ret!((false, "deposit refused"))
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

contract LiquidityLock(@"release", deployerId, ret) = {
  new pkCh, nowCh in {
    deployerIdOps!("pubKeyBytes", *deployerId, *pkCh) |
    lockNow!(*nowCh) |
    for (@pk <- pkCh; @now <- nowCh) {
      for (@s <- lockState) {
        if (pk != s.get("beneficiaryPubKey")) { lockState!(s) | ret!((false, "not beneficiary")) }
        else {
          if (s.get("funded") == false) { lockState!(s) | ret!((false, "not funded")) }
          else {
            if (s.get("released")) { lockState!(s) | ret!((false, "already released")) }
            else {
              if (now < s.get("untilHeight") && s.get("cancelled") == false) {
                lockState!(s) | ret!((false, "not yet"))
              } else {
                new wdCh in {
                  @lpPurse!("withdraw", (lpBrand, s.get("shares")), *wdCh) |
                  for (@w <- wdCh) {
                    match w {
                      (true, pay) => {
                        lockState!(s.set("released", true)) |
                        ret!((true, s.get("shares"), pay))
                      }
                      _ => { lockState!(s) | ret!((false, "withdraw refused")) }
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

contract LiquidityLock(@"info", ret) = {
  for (@s <<- lockState) {
    ret!((true, {
      "marketId": s.get("marketId"),
      "termsHash": s.get("termsHash"),
      "beneficiaryPubKey": s.get("beneficiaryPubKey"),
      "beneficiaryOwnerId": s.get("beneficiaryOwnerId"),
      "lpBrand": s.get("lpBrand"),
      "lpIssuer": s.get("lpIssuer"),
      "minShares": s.get("minShares"),
      "shares": s.get("shares"),
      "untilHeight": s.get("untilHeight"),
      "funded": s.get("funded"),
      "released": s.get("released"),
      "cancelled": s.get("cancelled"),
      "fundedAt": s.get("fundedAt")
    }))
  }
} |

contract lockAdminApply(@action, @nonce, ret) = {
  for (@s <- lockState) {
    if (nonce <= s.get("govNonce")) { lockState!(s) | ret!((false, "replay")) }
    else {
      if (action == "cancel") {
        lockState!(s.set("cancelled", true).set("govNonce", nonce)) | ret!((true, Nil))
      } else { lockState!(s) | ret!((false, "unknown action")) }
    }
  }
} |

contract LiquidityLock(@"admin", @nonce, @action, @args, @sigs, ret) = {
  for (@s <<- lockState) {
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
                    verifyAdmin!("lock:" ++ s.get("marketId"), nonce, action, args, sigs,
                                 admins, threshold, *okCh) |
                    for (@ok <- okCh) {
                      if (ok) { lockAdminApply!(action, nonce, *ret) }
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
