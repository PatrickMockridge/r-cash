import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import Pay from "./Pay";
import { usePreferences } from "../lib/preferences";
import { renderWithProviders, resetWallet, setFakeClient } from "../test/render";

describe("Pay default asset", () => {
  beforeEach(() => {
    resetWallet();
    usePreferences.setState({ displayCurrency: "USD" });
    setFakeClient({
      v4_currencies: async () => JSON.stringify([
        { code: "USD", kind: "stablecoin", stablecoinUri: "", custodyUri: "",
          paramsUri: "", vaultUri: "", liquidationUri: "", savingsUri: "", psmUri: "",
          bufferUri: "", paramsHash: "", sponsor: "", status: "active" },
      ]),
    });
  });

  it("defaults to the preferred currency when it is listed", async () => {
    renderWithProviders(<Pay />);
    await waitFor(() =>
      expect(screen.getByLabelText("Asset")).toHaveValue("USD"),
    );
  });
});
