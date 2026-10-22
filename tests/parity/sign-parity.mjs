// Independent TypeScript signer for the R0a parity gate.
//
// Adapted from RhoGov `src/chain/keys.ts` (Apache-2.0); modified for R-Cash to
// read a fixture emitted by the Rust client and to compare every value.
// The encoder intentionally does not include field 12 (attachments); the fixture
// has none, so for this vector the bytes are the same as the Rust encoder's.

import { readFileSync } from "node:fs";
import { secp256k1 } from "@noble/curves/secp256k1.js";
import { blake2b } from "@noble/hashes/blake2.js";
import { keccak_256 } from "@noble/hashes/sha3.js";

const hex = (b) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
const unhex = (s) => {
  const t = s.trim().replace(/^0x/, "");
  if (!/^[0-9a-fA-F]*$/.test(t) || t.length % 2) throw new Error("not base16");
  return new Uint8Array((t.match(/../g) ?? []).map((p) => parseInt(p, 16)));
};

const BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58(bytes) {
  let n = 0n;
  for (const b of bytes) n = (n << 8n) | BigInt(b);
  let out = "";
  while (n > 0n) {
    out = BASE58[Number(n % 58n)] + out;
    n /= 58n;
  }
  for (const b of bytes) {
    if (b !== 0) break;
    out = BASE58[0] + out;
  }
  return out;
}

function varint(n) {
  const out = [];
  let v = BigInt(n);
  do {
    let byte = Number(v & 0x7fn);
    v >>= 7n;
    if (v > 0n) byte |= 0x80;
    out.push(byte);
  } while (v > 0n);
  return out;
}
const fieldVarint = (f, v) => (v === 0 ? [] : [...varint((f << 3) | 0), ...varint(v)]);
function fieldString(f, v) {
  if (!v) return [];
  const b = new TextEncoder().encode(v);
  return [...varint((f << 3) | 2), ...varint(b.length), ...b];
}

function encodeDeployData(d) {
  return new Uint8Array([
    ...fieldString(2, d.term),
    ...fieldVarint(3, d.timestamp),
    ...fieldVarint(7, d.phloPrice),
    ...fieldVarint(8, d.phloLimit),
    ...fieldVarint(10, d.validAfterBlockNumber),
    ...fieldString(11, d.shardId),
  ]);
}

function revAddressOf(secretHex) {
  const pub = secp256k1.getPublicKey(unhex(secretHex), false);
  const eth = hex(keccak_256(pub.slice(1))).slice(-40);
  const payload = new Uint8Array([0, 0, 0, 0, ...keccak_256(unhex(eth))]);
  const checksum = blake2b(payload, { dkLen: 32 }).slice(0, 4);
  return base58(new Uint8Array([...payload, ...checksum]));
}

const fixturePath = process.argv[2];
if (!fixturePath) {
  console.error("usage: node sign-parity.mjs <fixture.json>");
  process.exit(2);
}
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const encoded = encodeDeployData(fixture.data);
const digest = blake2b(encoded, { dkLen: 32 });
const signature = hex(
  secp256k1.sign(digest, unhex(fixture.secret), { prehash: false, format: "der" }),
);
const deployer = hex(secp256k1.getPublicKey(unhex(fixture.secret), false));
const address = revAddressOf(fixture.secret);

const checks = [
  ["encoded deploy bytes", hex(encoded), fixture.encoded],
  ["public key", deployer, fixture.deployer],
  ["signature / deploy id", signature, fixture.signature],
  ["address", address, fixture.address],
];
let failed = false;
for (const [name, actual, expected] of checks) {
  if (actual !== expected) {
    failed = true;
    console.error(`FAIL ${name}\n  rust: ${expected}\n  ts:   ${actual}`);
  } else {
    console.log(`PASS ${name}: ${actual.slice(0, 24)}...`);
  }
}
process.exit(failed ? 1 : 0);
