import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import Accounts from "./Accounts";
import { usePreferences } from "../lib/preferences";
import { renderWithProviders, resetWallet, setFakeClient } from "../test/render";

function currency(code: string) {
  return {
    code, kind: "stablecoin", stablecoinUri: `sc-${code}`, custodyUri: "",
    paramsUri: "", vaultUri: "", liquidationUri: "", savingsUri: "", psmUri: "",
    bufferUri: "", paramsHash: "", sponsor: "", status: "active",
  };
}

describe("Accounts in the preferred currency", () => {
  beforeEach(() => {
    resetWallet();
    usePreferences.setState({ displayCurrency: "USD" });
    setFakeClient({
      v4_currencies: async () => JSON.stringify([currency("USD"), currency("NGN")]),
      rev_balance: async () => JSON.stringify({ baseUnits: 100_000_000, rev: "1" }),
      v4_balance: async (asset: string) =>
        JSON.stringify({ baseUnits: asset === "NGN" ? 500_000_000 : 100_000_000 }),
      v4_price: async (asset: string) =>
        JSON.stringify({ rate: asset === "USD" ? 100_000_000 : asset === "REV" ? 5_000_000 : 65_000 }),
      public_key: () => "fixture-pub",
    });
  });

  it("shows a preferred total and per-asset converted values", async () => {
    renderWithProviders(<Accounts />);
    expect(await screen.findByText("Total in USD")).toBeInTheDocument();
    expect(await screen.findByText("NGN purse")).toBeInTheDocument();
    expect(await screen.findByText("5")).toBeInTheDocument();
    expect(screen.queryByText("no price")).not.toBeInTheDocument();
  });
});
