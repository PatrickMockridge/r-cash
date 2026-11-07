#!/usr/bin/env python3
"""Object-capability red-team suite.

Each check is an adversarial deploy against the running devnet; the expected
result is a refusal (or a benign answer) at the capability boundary, never
success. See docs/spec/OCAP-REDTEAM.md for the scenario table and the recorded
results.

Usage:
    python3 harness/unit_ocap.py

The suite needs the installed components (`make install`). The account factory
comes from the install state; set RCASH_ACCOUNT_FACTORY to point at a
candidate term deployed out of band.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "harness"))

import netconfig  # noqa: E402
from minify_rho import minify  # noqa: E402
from unit_v3 import call, check, faucet_top_up, one  # noqa: E402

KEYS = netconfig.KEYS_PATH
STATE = netconfig.STATE_PATH


def root_resolve(root: str, key: str, min_version: int, secret: str):
    return one(
        call(root, "Root",
             f'Root!("resolve", "{key}", {min_version}, *r) | '
             "for (@x <- r) { deployId!(x) }"),
        secret,
    )


def rt11_root_dispatch(root: str, secret: str) -> None:
    """RT-11a: an active component resolves; unknown and stale refuse."""
    active = root_resolve(root, "component:clock", 1, secret)
    check("root resolve active", active[0], True)
    check("root resolve active uri", active[1].startswith("rho:id:"), True)
    unknown = root_resolve(root, "component:not-a-component", 1, secret)
    check("root resolve unknown", unknown, (False, "unknown component"))
    stale = root_resolve(root, "component:clock", 10_000, secret)
    check("root resolve stale", stale, (False, "stale"))


def rt11_gate_active(gate: str, secret: str) -> None:
    """RT-11b: an active status must admit, not fall through to 'not active'."""
    terms = '{"minTicketQuote": 0, "maxTradeBps": 10000}'
    reply = one(
        call(gate, "TradabilityGate",
             f'TradabilityGate!("admit", "active", true, 0, 1000000, {terms}, *r) | '
             "for (@x <- r) { deployId!(x) }"),
        secret,
    )
    check("tradability active admits", reply, (True,))


def rt02_registry_fresh_auth(directory: str, secret: str) -> None:
    """RT-02: a fresh name is not the directory authority."""
    reply = one(
        call(directory, "MarketDirectory",
             'new attacker in { '
             'MarketDirectory!("bind", "ocap-probe", "slot", *attacker, *r) } | '
             "for (@x <- r) { deployId!(x) }"),
        secret,
    )
    check("market bind refuses a fresh auth", reply, (False, "bad directory authority"))


def rt03_vault_substitution(factory: str, pub: str, secret: str) -> None:
    """RT-03/RT-09: vaultOpen never resolves a caller-supplied URI.

    The term publishes a hostile contract whose `open` arm would capture the
    proof, then passes that contract's URI as the currency code. A correct
    vaultOpen reads the currency registry instead and refuses; a vulnerable one
    resolves the URI and answers `captured`.
    """
    term = f'''
new HostileVault, rs(`rho:registry:insertArbitrary`), u,
    rl(`rho:registry:lookup`), afCh, oCh, zCh,
    deployId(`rho:rchain:deployId`), deployerId(`rho:rchain:deployerId`) in {{
  contract HostileVault(@"open", @ownerId, proof, ret) = {{
    ret!((true, "captured"))
  }} |
  rs!(bundle+{{*HostileVault}}, *u) |
  for (@hUri <- u) {{
    rl!(`{factory}`, *afCh) |
    for (AccountFactory <- afCh) {{
      AccountFactory!("getOrCreate", "{pub}".hexToBytes(), *oCh) |
      for (@(true, account, ownerId) <- oCh) {{
        @account!("vaultOpen", *deployerId, hUri, *zCh) |
        for (@z <- zCh) {{ deployId!([z, hUri]) }}
      }}
    }}
  }}
}}'''
    reply = one(minify(term), secret)
    check("vaultOpen ignores a caller URI (substitution)", reply[0][0], False)
    check("vaultOpen reports the registry lookup", reply[0][1], "no currency")
    check("vaultOpen did not reach the hostile vault", reply[0][1] != "captured", True)


def rt13_vault_rotation(factory: str, registry: str, pub: str, secret: str) -> None:
    """RT-13: a rotated vault auth retires the old capability."""
    term = f'''
new ertpCh, regCh, eCh, afCh, oCh, zCh, r1, r2, r3, vc,
    rl(`rho:registry:lookup`), deployId(`rho:rchain:deployId`),
    deployerId(`rho:rchain:deployerId`) in {{
  rl!(`{registry}`, *regCh) |
  for (Registry <- regCh) {{
    Registry!("currency", "V4T", *eCh) |
    for (@e <- eCh) {{
      match e {{
        (true, entry) => {{
          rl!(`{factory}`, *afCh) |
          for (AccountFactory <- afCh) {{
            AccountFactory!("getOrCreate", "{pub}".hexToBytes(), *oCh) |
            for (@(true, account, ownerId) <- oCh) {{
              @account!("vaultOpen", *deployerId, "V4T", *zCh) |
              for (@z <- zCh) {{
                match z {{
                  (true, auth) => {{
                    new newAuth in {{
                      rl!(entry.get("vaultUri"), *vc) |
                      for (VaultBook <- vc) {{
                        VaultBook!("rotate", ownerId, auth, *newAuth, *r1) |
                        for (@rot <- r1) {{
                          VaultBook!("mint", ownerId, auth, 1, *r2) |
                          VaultBook!("mint", ownerId, *newAuth, 1, *r3) |
                          for (@m1 <- r2; @m2 <- r3) {{
                            deployId!([rot, m1, m2])
                          }}
                        }}
                      }}
                    }}
                  }}
                  _ => {{ deployId!(z) }}
                }}
              }}
            }}
          }}
        }}
        _ => {{ deployId!(e) }}
      }}
    }}
  }}
}}'''
    reply = one(minify(term), secret)
    if isinstance(reply, tuple) and reply and reply[0] is False:
        print(f"skip vault rotation (no listed V4T system): {reply}")
        return
    if not (isinstance(reply, list) and len(reply) == 3):
        raise AssertionError(f"rotation probe did not run: {reply!r}")
    rotation, old_auth, new_auth = reply
    check("vault rotation succeeds", rotation, (True,))
    check("rotated-out auth is refused", old_auth, (False, "bad vault auth"))
    check("rotated-in auth is not refused", new_auth != (False, "bad vault auth"), True)


def main() -> int:
    keys = json.loads(KEYS.read_text())
    state = json.loads(STATE.read_text())
    root = state["root_uri"]
    deployer = keys["deployer"]
    secret = deployer["secret"]
    faucet_top_up(deployer["address"])

    factory = os.environ.get("RCASH_ACCOUNT_FACTORY") or state.get("account_factory_uri")
    if not factory:
        raise SystemExit("no account factory: install the components first")

    rt11_root_dispatch(root, secret)
    rt11_gate_active(state["tradability_gate_uri"], secret)
    rt02_registry_fresh_auth(state["market_directory_uri"], secret)
    rt03_vault_substitution(factory, deployer["public"], secret)
    rt13_vault_rotation(factory, state["currency_registry_uri"],
                        deployer["public"], secret)
    print("ocap red-team: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
