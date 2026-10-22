import { describe, expect, it } from "vitest";
import { claimFragment, claimLink, parseClaim } from "./claim";

describe("claim links", () => {
  const secret = "ab".repeat(32);

  it("parses a fragment and a full URL", () => {
    expect(parseClaim(`#/claim/7/${secret}`)).toEqual({ id: 7, secret });
    expect(parseClaim(`http://localhost:5173/#/claim/12/${secret.toUpperCase()}`)).toEqual({
      id: 12,
      secret,
    });
  });

  it("refuses malformed input", () => {
    expect(parseClaim("#/claim/7/short")).toBeNull();
    expect(parseClaim("#/claim/x/" + secret)).toBeNull();
    expect(parseClaim(secret)).toBeNull();
  });

  it("round-trips", () => {
    expect(parseClaim(claimFragment(3, secret))).toEqual({ id: 3, secret });
    expect(claimLink("http://localhost:5173/", 3, secret)).toBe(
      `http://localhost:5173/#/claim/3/${secret}`,
    );
  });
});
