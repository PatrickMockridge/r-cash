// Directory: names -> component URIs, assetId -> {kind, controllerKey, decimals}.
// State is seeded by the bootstrap term (which holds the private `state` channel):
//   {names: Map, assets: Map, locked: Bool, admins: List, threshold: Int, govNonce: Int}
// Bootstrap registration is only possible while locked == false; the bootstrap deploy registers
// and locks in one atomic term. Admin-signed registration after the lock is phase 2.
// Rholang note: method calls are not chained here; each `.get`/`.set` is a single call bound by
// a match, which the parser accepts unambiguously.

contract Directory(@"get", @name, ret) = {
  for (@s <<- state) {
    match s.get("names") {
      Nil => ret!((false, "unknown"))
      names => {
        match names.get(name) {
          Nil => ret!((false, "unknown"))
          uri => ret!((true, uri))
        }
      }
    }
  }
} |

contract Directory(@"asset", @assetId, ret) = {
  for (@s <<- state) {
    match s.get("assets") {
      Nil => ret!((false, "unknown asset"))
      assets => {
        match assets.get(assetId) {
          Nil => ret!((false, "unknown asset"))
          meta => ret!((true, meta))
        }
      }
    }
  }
} |

contract Directory(@"register", @name, @uri, ret) = {
  for (@s <- state) {
    if (s.get("locked")) {
      state!(s) |
      ret!((false, "locked"))
    } else {
      match s.get("names") {
        Nil => { state!(s) | ret!((false, "no names map")) }
        names => {
          state!(s.set("names", names.set(name, uri))) |
          ret!((true, Nil))
        }
      }
    }
  }
} |

contract Directory(@"registerAsset", @assetId, @kind, @controller, @decimals, ret) = {
  for (@s <- state) {
    if (s.get("locked")) {
      state!(s) |
      ret!((false, "locked"))
    } else {
      match s.get("assets") {
        Nil => { state!(s) | ret!((false, "no assets map")) }
        assets => {
          state!(s.set("assets", assets.set(
            assetId,
            {"kind": kind, "controllerKey": controller, "decimals": decimals}
          ))) |
          ret!((true, Nil))
        }
      }
    }
  }
} |

contract Directory(@"lock", ret) = {
  for (@s <- state) {
    state!(s.set("locked", true)) |
    ret!((true, Nil))
  }
} |

contract Directory(@"names", ret) = {
  for (@s <<- state) {
    match s.get("names") {
      Nil => ret!((true, {}))
      names => ret!((true, names))
    }
  }
} |

contract Directory(@"admin", @nonce, @action, @args, @sigs, ret) = {
  ret!((false, "admin actions are phase 2"))
} |
