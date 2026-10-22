// Guard: M-of-N admin signature verification over a canonical payload.
//
// Off-chain canonical string (tools/sign_payload.py):
//   "rcash:admin:v1|<component>|<nonce>|<action>|<arg0>,<arg1>,..."
// The contract hashes the UTF-8 bytes with blake2b256 and verifies DER secp256k1 signatures
// with `secp256k1Verify(hash, sig, pubkey)`.
//
// Captured system channels: hash (`rho:crypto:blake2b256Hash`), verify
// (`rho:crypto:secp256k1Verify`). Helper names are declared by the including component.

contract guardArgsToString(@args, ret) = {
  if (args.length() == 0) {
    ret!("")
  } else {
    match args.nth(0) {
      a => {
        new restCh in {
          guardArgsAppend!(args, 1, a.toString(), *restCh) |
          for (@s <- restCh) { ret!(s) }
        }
      }
    }
  }
} |

contract guardArgsAppend(@args, @i, @acc, ret) = {
  if (i >= args.length()) {
    ret!(acc)
  } else {
    match args.nth(i) {
      a => {
        guardArgsAppend!(args, i + 1, acc ++ "," ++ a.toString(), *ret)
      }
    }
  }
} |

contract guardAnySig(@digest, @sigs, @j, @key, ret) = {
  if (j >= sigs.length()) {
    ret!(false)
  } else {
    match sigs.nth(j) {
      sig => {
        new vCh in {
          verify!(digest, sig, key, *vCh) |
          for (@ok <- vCh) {
            if (ok) { ret!(true) } else { guardAnySig!(digest, sigs, j + 1, key, *ret) }
          }
        }
      }
    }
  }
} |

contract guardCount(@digest, @sigs, @i, @count, @keys, @threshold, ret) = {
  if (i >= keys.length()) {
    ret!(count >= threshold)
  } else {
    match keys.nth(i) {
      key => {
        new anyCh in {
          guardAnySig!(digest, sigs, 0, key, *anyCh) |
          for (@any <- anyCh) {
            if (any) { guardCount!(digest, sigs, i + 1, count + 1, keys, threshold, *ret) }
            else { guardCount!(digest, sigs, i + 1, count, keys, threshold, *ret) }
          }
        }
      }
    }
  }
} |

contract verifyAdmin(@component, @nonce, @action, @args, @sigs, @keys, @threshold, ret) = {
  new strCh, hashCh, okCh in {
    guardArgsToString!(args, *strCh) |
    for (@argStr <- strCh) {
      match "rcash:admin:v1|" ++ component ++ "|" ++ nonce.toString() ++ "|" ++ action ++ "|" ++ argStr {
        payload => {
          hash!(payload.toUtf8Bytes(), *hashCh) |
          for (@digest <- hashCh) {
            guardCount!(digest, sigs, 0, 0, keys, threshold, *okCh) |
            for (@ok <- okCh) { ret!(ok) }
          }
        }
      }
    }
  }
} |
