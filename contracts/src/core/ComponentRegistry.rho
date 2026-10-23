// ComponentRegistry: name -> live contract channel. A large contract cannot always be wrapped in
// a bundle on this node (the bundle free-variable check rejects some nested captures), so the
// bootstrap holds the live name here instead of installing a bundle. The registry is a simple
// contract and bundles cleanly.
//
// State is seeded by the bootstrap: componentsState!({}).

contract Components(@"set", @key, cap, ret) = {
  for (@s <- componentsState) {
    if (s.get("locked")) {
      componentsState!(s) |
      ret!((false, "locked"))
    } else {
      componentsState!(s.set(key, *cap)) |
      ret!((true, Nil))
    }
  }
} |


contract Components(@"setValue", @key, @value, ret) = {
  for (@s <- componentsState) {
    if (s.get("locked")) {
      componentsState!(s) |
      ret!((false, "locked"))
    } else {
      componentsState!(s.set(key, value)) |
      ret!((true, Nil))
    }
  }
} |

contract Components(@"lock", ret) = {
  for (@s <- componentsState) {
    componentsState!(s.set("locked", true)) |
    ret!((true, Nil))
  }
} |

contract Components(@"get", @key, ret) = {
  for (@s <<- componentsState) {
    match s.get(key) {
      Nil => ret!((false, "unknown component"))
      cap => ret!((true, cap))
    }
  }
} |

contract Components(@"has", @key, ret) = {
  for (@s <<- componentsState) {
    match s.get(key) {
      Nil => ret!((true, false))
      cap => ret!((true, true))
    }
  }
} |
