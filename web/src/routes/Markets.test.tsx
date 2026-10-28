import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import Markets from "./Markets";
import { usePreferences } from "../lib/preferences";
import { renderWithProviders, resetWallet, setFakeClient } from "../test/render";

describe("Markets mesh", () => {
  beforeEach(() => {
    resetWallet();
    usePreferences.setState({ displayCurrency: "USD" });
    setFakeClient({
      v4_markets: async () =>
        JSON.stringify([
          { marketId: "NGN/USD:v1", slug: "ngn-usd-v1", base: "NGN", quote: "USD",
            version: 1, termsHash: "aa", status: "active" },
        ]),
      v4_price: async () => JSON.stringify({
        rate: 65_000, fresh: true, basePrice: 65_000, quotePrice: 100_000_000,
        baseAge: 1, quoteAge: 1,
      }),
    });
  });

  it("renders the full mesh with active and unlisted pairs", async () => {
    renderWithProviders(<Markets />);
    expect(await screen.findByText("Currency mesh")).toBeInTheDocument();
    expect(await screen.findAllByText("active")).not.toHaveLength(0);
    expect(await screen.findAllByText("unlisted")).not.toHaveLength(0);
    expect(screen.getByText(/120 supported pairs/i)).toBeInTheDocument();
  });
});
