import { useState } from "react";
import { AccountsPage } from "./pages/AccountsPage";
import { EsppPage } from "./pages/EsppPage";
import { ImportPage } from "./pages/ImportPage";
import { MonthlyValuesPage } from "./pages/MonthlyValuesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PassiveIncomePage } from "./pages/PassiveIncomePage";
import { Trading212Page } from "./pages/Trading212Page";
import type { Currency } from "./types";

type Tab = "overview" | "accounts" | "monthly" | "trading212" | "espp" | "passive" | "import";

const CURRENCIES: Currency[] = ["EUR", "USD", "PLN"];

// These tabs show data in its own native currency (or, for Import, don't use
// currency at all) — a conversion picker wouldn't do anything there.
const TABS_WITHOUT_CURRENCY_PICKER: Tab[] = ["import", "trading212", "espp"];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [currency, setCurrency] = useState<Currency>("EUR");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">Worthflow</div>
        {!TABS_WITHOUT_CURRENCY_PICKER.includes(tab) && (
          <select value={currency} onChange={(e) => setCurrency(e.target.value as Currency)}>
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}
      </header>

      <nav className="tabs">
        <button className={`tab-button ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          Overview
        </button>
        <button className={`tab-button ${tab === "accounts" ? "active" : ""}`} onClick={() => setTab("accounts")}>
          Accounts
        </button>
        <button className={`tab-button ${tab === "monthly" ? "active" : ""}`} onClick={() => setTab("monthly")}>
          Monthly values
        </button>
        <button className={`tab-button ${tab === "trading212" ? "active" : ""}`} onClick={() => setTab("trading212")}>
          Trading212
        </button>
        <button className={`tab-button ${tab === "espp" ? "active" : ""}`} onClick={() => setTab("espp")}>
          ESPP / RSU
        </button>
        <button className={`tab-button ${tab === "passive" ? "active" : ""}`} onClick={() => setTab("passive")}>
          Passive income
        </button>
        <button className={`tab-button ${tab === "import" ? "active" : ""}`} onClick={() => setTab("import")}>
          Import
        </button>
      </nav>

      {tab === "overview" && <OverviewPage currency={currency} />}
      {tab === "accounts" && <AccountsPage currency={currency} />}
      {tab === "monthly" && <MonthlyValuesPage currency={currency} />}
      {tab === "trading212" && <Trading212Page />}
      {tab === "espp" && <EsppPage />}
      {tab === "passive" && <PassiveIncomePage currency={currency} />}
      {tab === "import" && <ImportPage />}
    </div>
  );
}
