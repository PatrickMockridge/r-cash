import { describe, expect, it } from "vitest";
import { formatUnits, parseUnits } from "./format";

describe("fixed-point formatting", () => {
  it("formats base units exactly", () => {
    expect(formatUnits(100_000_000)).toBe("1");
    expect(formatUnits("123456789")).toBe("1.23456789");
    expect(formatUnits(1)).toBe("0.00000001");
    expect(formatUnits(0)).toBe("0");
    expect(formatUnits(-25_000_000)).toBe("-0.25");
  });

  it("parses decimals exactly", () => {
    expect(parseUnits("1")).toBe(100_000_000n);
    expect(parseUnits("0.00000001")).toBe(1n);
    expect(parseUnits("1.25")).toBe(125_000_000n);
    expect(() => parseUnits("0.000000001")).toThrow();
    expect(() => parseUnits("1e8")).toThrow();
    expect(() => parseUnits("")).toThrow();
  });
});
