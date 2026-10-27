import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Accounts from "./routes/Accounts";
import Claim from "./routes/Claim";
import Convert from "./routes/Convert";
import Earn from "./routes/Earn";
import Governance from "./routes/Governance";
import History from "./routes/History";
import Liquidity from "./routes/Liquidity";
import Markets from "./routes/Markets";
import Pay from "./routes/Pay";
import Receive from "./routes/Receive";
import Redeem from "./routes/Redeem";
import Settings from "./routes/Settings";
import Vault from "./routes/Vault";
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
        <Route path="claim/:uri/:secret" element={<Claim />} />
        <Route path="vault" element={<Vault />} />
        <Route path="earn" element={<Earn />} />
        <Route path="redeem" element={<Redeem />} />
        <Route path="markets" element={<Markets />} />
        <Route path="liquidity" element={<Liquidity />} />
        <Route path="history" element={<History />} />
        <Route path="governance" element={<Governance />} />
        <Route
          path="batch"
          element={
            <Disabled
              title="Batch payouts"
              reason="Batch payouts are not in the v0.4 protocol. Paying several recipients today means several separate deploys, which is not atomic, so this screen does not pretend otherwise."
            />
          }
        />
        <Route
          path="ramps"
          element={
            <Disabled
              title="Local ramps"
              reason="A live ramp is a licensed off-chain partner, not an on-chain contract. v0.4 has no ramp registry; payouts happen off-chain with the recipient's key."
            />
          }
        />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
