import { NavLink, Outlet } from "react-router-dom";
import { useWallet } from "../lib/store";
import { shortId } from "../lib/format";

const links = [
  ["/", "Accounts"],
  ["/receive", "Receive"],
  ["/pay", "Pay"],
  ["/vault", "Vault"],
  ["/earn", "Earn"],
  ["/redeem", "Redeem"],
  ["/markets", "Markets"],
  ["/convert", "Convert"],
  ["/liquidity", "Liquidity"],
  ["/history", "History"],
  ["/governance", "Governance"],
  ["/settings", "Settings"],
] as const;

export default function Layout() {
  const { status, address, lock } = useWallet();

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">R</span>
          <div>
            <strong>R-Cash</strong>
            <span className="tagline">multi-currency account · devnet</span>
          </div>
        </div>
        <div className="wallet-chip">
          {status === "unlocked" && address ? (
            <>
              <span className="mono" title={address}>
                {shortId(address, 6)}
              </span>
              <button className="ghost" onClick={lock}>
                Lock
              </button>
            </>
          ) : (
            <span className="muted">wallet locked</span>
          )}
        </div>
      </header>

      <nav className="tabs">
        {links.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => (isActive ? "tab active" : "tab")}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <main className="content">
        <Outlet />
      </main>

      <footer className="footer">
        <span>Devnet only. No real funds.</span>
        <a href="https://github.com/PatrickMockridge/r-cash" target="_blank" rel="noreferrer">
          Source (AGPL-3.0)
        </a>
      </footer>
    </div>
  );
}
