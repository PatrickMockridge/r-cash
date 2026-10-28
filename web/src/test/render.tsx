import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import type { Rcash } from "../wasm";
import { useWallet } from "../lib/store";

export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

export function setFakeClient(client: Partial<Rcash>) {
  useWallet.setState({
    status: "unlocked",
    client: client as unknown as Rcash,
    address: "1111fixture",
  });
}

export function resetWallet() {
  useWallet.setState({ status: "locked", client: null, address: null });
}
