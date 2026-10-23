// Canonical string helpers for market terms, feed policy and parameter hashes.
//
// The canonical form is `schema|value0|value1|...`; the hash is BLAKE2b-256 of its UTF-8
// bytes. Rholang, Rust and Python must agree; tests/terms/terms-vectors.json pins it.

contract termsJoin(@items, @i, @acc, ret) = {
  if (i >= items.length()) {
    ret!(acc)
  } else {
    match items.nth(i) {
      x => { termsJoin!(items, i + 1, acc ++ "|" ++ x.toString(), *ret) }
    }
  }
} |

contract termsCanonical(@schema, @items, ret) = {
  if (items.length() == 0) {
    ret!(schema)
  } else {
    match items.nth(0) {
      x => { termsJoin!(items, 1, schema ++ "|" ++ x.toString(), *ret) }
    }
  }
} |

// `hashCh` is the captured `rho:crypto:blake2b256Hash`. Pass it as a name: `*hash`.
contract termsHash(@hashCh, @schema, @items, ret) = {
  new cCh in {
    termsCanonical!(schema, items, *cCh) |
    for (@text <- cCh) {
      @hashCh!(text.toUtf8Bytes(), *ret)
    }
  }
} |
