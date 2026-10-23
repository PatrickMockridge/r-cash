import { describe, expect, it } from "vitest";
import { claimFragment, claimLink, parseClaim } from "./claim";

describe("claim links", () => {
  const uri = "rho:id:abc123";
  const secret = "ab".repeat(32);

  it("parses a fragment and a full URL", () => {
    expect(parseClaim(`#/claim/${uri}/${secret}`)).toEqual({ uri, secret });
    expect(parseClaim(`http://localhost:5173/#/claim/${uri}/${secret.toUpperCase()}`)).toEqual({
      uri,
      secret,
    });
  });

  it("refuses malformed input", () => {
    expect(parseClaim(`#/claim/${uri}/short`)).toBeNull();
    expect(parseClaim("#/claim/not-a-uri/" + secret)).toBeNull();
    expect(parseClaim(secret)).toBeNull();
  });

  it("round-trips", () => {
    expect(parseClaim(claimFragment(uri, secret))).toEqual({ uri, secret });
    expect(claimLink("http://localhost:5173/", uri, secret)).toBe(
      `http://localhost:5173/#/claim/${uri}/${secret}`,
    );
  });
});
