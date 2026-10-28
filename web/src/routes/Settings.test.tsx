import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings";
import { usePreferences } from "../lib/preferences";
import { renderWithProviders, resetWallet, setFakeClient } from "../test/render";

vi.mock("../lib/db", () => ({
  listKeystores: async () => [],
  exportKeystore: async () => "{}",
}));

describe("Settings preferred currency", () => {
  beforeEach(() => {
    resetWallet();
    setFakeClient({});
    usePreferences.setState({ displayCurrency: "USD" });
  });

  it("defaults to USD and persists a user choice", async () => {
    renderWithProviders(<Settings />);
    const select = screen.getByLabelText(/Default currency/i);
    expect(select).toHaveValue("USD");
    await userEvent.selectOptions(select, "ZAR");
    expect(localStorage.getItem("rcash.displayCurrency")).toBe("ZAR");
    expect(usePreferences.getState().displayCurrency).toBe("ZAR");
  });

  it("groups majors before local currencies", () => {
    renderWithProviders(<Settings />);
    const groups = screen.getAllByRole("group").map((group) => group.getAttribute("label"));
    expect(groups).toEqual(["Majors", "Local currencies"]);
  });
});
