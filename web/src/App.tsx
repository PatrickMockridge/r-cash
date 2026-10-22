import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Accounts from "./routes/Accounts";
import Claim from "./routes/Claim";
import Convert from "./routes/Convert";
import Liquidity from "./routes/Liquidity";
import Mint from "./routes/Mint";
import Pay from "./routes/Pay";
import Receive from "./routes/Receive";
import Settings from "./routes/Settings";
import Disabled from "./routes/Disabled";
import { useWallet } from "./lib/store";

export default function App() {
  const boot = useWallet((state) => state.boot);
  useEffect(() => {
    void boot();
  }, [boot]);

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Accounts />} />
        <Route path="receive" element={<Receive />} />
        <Route path="convert" element={<Convert />} />
        <Route path="pay" element={<Pay />} />
        <Route path="claim/:id/:secret" element={<Claim />} />
        <Route path="liquidity" element={<Liquidity />} />
        <Route path="mint" element={<Mint />} />
        <Route
          path="batch"
          element={
            <Disabled
              title="Batch payouts"
              reason="sendBatch is not in the v0.1 protocol. Paying several recipients today means several separate deploys, which is not atomic, so this screen does not pretend otherwise."
            />
          }
        />
        <Route
          path="ramps"
          element={
            <Disabled
              title="Local ramps"
              reason="A live ramp is a licensed off-chain partner, not an on-chain contract. v0.1 has no RampRegistry; payouts happen off-chain with the recipient's key."
            />
          }
        />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
