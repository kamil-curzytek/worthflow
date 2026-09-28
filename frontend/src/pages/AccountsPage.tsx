import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, ApiError } from "../api/client";
import { CHART_PALETTE, TIME_PERIODS } from "../constants";
import { formatDate, formatMoney, monthsAgoIso } from "../format";
import type { Account, AccountType, AssetClass, Currency } from "../types";

const ACCOUNT_TYPES: AccountType[] = [
  "checking",
  "savings",
  "brokerage",
  "cash",
  "crypto",
  "pension",
  "equity_compensation",
  "other",
];
const ASSET_CLASSES: AssetClass[] = ["cash", "trading", "crypto", "equity_compensation", "other"];
const CURRENCIES: Currency[] = ["EUR", "USD", "PLN"];

export function AccountsPage({ currency }: { currency: Currency }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [trends, setTrends] = useState<Record<string, { date: string; value: string }[]>>({});
  const [periodMonths, setPeriodMonths] = useState<number | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    api.listAccounts(showInactive).then((list) => {
      setAccounts(list);
      setSelectedIds((prev) => {
        if (prev.size > 0) return prev;
        return list.length > 0 ? new Set([list[0].id]) : prev;
      });
    });
  }

  useEffect(reload, [showInactive]);

  useEffect(() => {
    if (selectedIds.size === 0) {
      setTrends({});
      return;
    }
    let cancelled = false;
    const start = periodMonths ? monthsAgoIso(periodMonths) : undefined;
    Promise.all(
      [...selectedIds].map((id) =>
        api.accountTrend(id, currency, start).then((res) => [id, res.points] as const),
      ),
    ).then((entries) => {
      if (!cancelled) setTrends(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [selectedIds, currency, periodMonths]);

  function toggleSelected(accountId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(accountId)) next.delete(accountId);
      else next.add(accountId);
      return next;
    });
  }

  const chartData = useMemo(() => {
    const dateSet = new Set<string>();
    Object.values(trends).forEach((points) => points.forEach((p) => dateSet.add(p.date)));
    const dates = [...dateSet].sort();
    return dates.map((date) => {
      const row: Record<string, string | number> = { date: formatDate(date) };
      for (const id of selectedIds) {
        const point = trends[id]?.find((p) => p.date === date);
        if (point) row[id] = Number(point.value);
      }
      return row;
    });
  }, [trends, selectedIds]);

  const selectedAccounts = accounts.filter((a) => selectedIds.has(a.id));
  const hasEnoughData = Object.values(trends).some((points) => points.length >= 2);

  return (
    <div>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="card-title" style={{ margin: 0 }}>
            Accounts
          </p>
          <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              Show inactive
            </label>
            <button className="secondary" onClick={() => setShowAddForm((v) => !v)}>
              {showAddForm ? "Cancel" : "+ Add account"}
            </button>
          </div>
        </div>

        {showAddForm && (
          <AddAccountForm
            onCreated={() => {
              setShowAddForm(false);
              reload();
            }}
            onError={setError}
          />
        )}
        {error && <div className="warning-list">{error}</div>}

        <table>
          <thead>
            <tr>
              <th>Plot</th>
              <th>Name</th>
              <th>Type</th>
              <th>Asset class</th>
              <th>Currency</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr
                key={a.id}
                onClick={() => toggleSelected(a.id)}
                style={{
                  cursor: "pointer",
                  opacity: a.is_active ? 1 : 0.55,
                  background: selectedIds.has(a.id)
                    ? "color-mix(in srgb, var(--accent) 8%, transparent)"
                    : undefined,
                }}
              >
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(a.id)}
                    onChange={() => toggleSelected(a.id)}
                  />
                </td>
                <td>{a.name}</td>
                <td>{a.type}</td>
                <td>{a.asset_class}</td>
                <td>{a.currency}</td>
                <td>{a.is_active ? "Active" : "Inactive"}</td>
                <td>
                  {a.is_active ? (
                    <button
                      className="secondary"
                      style={{ padding: "4px 10px", fontSize: 12 }}
                      onClick={(e) => {
                        e.stopPropagation();
                        api.deactivateAccount(a.id).then(reload);
                      }}
                    >
                      Deactivate
                    </button>
                  ) : (
                    <button
                      className="secondary"
                      style={{ padding: "4px 10px", fontSize: 12 }}
                      onClick={(e) => {
                        e.stopPropagation();
                        api.activateAccount(a.id).then(reload);
                      }}
                    >
                      Activate
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {accounts.length === 0 && (
          <div className="empty-state">No accounts yet. Import your data or add one manually.</div>
        )}
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="card-title" style={{ margin: 0 }}>
            {selectedAccounts.length === 0
              ? "Trend"
              : selectedAccounts.length === 1
                ? `${selectedAccounts[0].name} — trend`
                : `${selectedAccounts.length} accounts — trend`}
          </p>
          <div style={{ display: "flex", gap: 4 }}>
            {TIME_PERIODS.map((p) => (
              <button
                key={p.label}
                className={periodMonths === p.months ? "primary" : "secondary"}
                style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => setPeriodMonths(p.months)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {selectedAccounts.length === 0 ? (
          <div className="empty-state">Tick one or more accounts above to plot their trend.</div>
        ) : !hasEnoughData ? (
          <div className="empty-state">Not enough history for the selected account(s) yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="var(--text-muted)" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="var(--text-muted)"
                tickFormatter={(v) => formatMoney(v, currency)}
                width={90}
              />
              <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
              {selectedAccounts.length > 1 && <Legend />}
              {selectedAccounts.map((a, i) => (
                <Line
                  key={a.id}
                  type="monotone"
                  dataKey={a.id}
                  name={a.name}
                  stroke={CHART_PALETTE[i % CHART_PALETTE.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

function AddAccountForm({
  onCreated,
  onError,
}: {
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AccountType>("checking");
  const [assetClass, setAssetClass] = useState<AssetClass>("cash");
  const [currency, setCurrency] = useState<Currency>("EUR");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      await api.createAccount({ name: name.trim(), type, asset_class: assetClass, currency });
      onCreated();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Failed to create account");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="form-row"
      style={{ marginTop: 12, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}
    >
      <div className="form-field">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Revolut" />
      </div>
      <div className="form-field">
        <label>Type</label>
        <select value={type} onChange={(e) => setType(e.target.value as AccountType)}>
          {ACCOUNT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <div className="form-field">
        <label>Asset class</label>
        <select value={assetClass} onChange={(e) => setAssetClass(e.target.value as AssetClass)}>
          {ASSET_CLASSES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <div className="form-field">
        <label>Currency</label>
        <select value={currency} onChange={(e) => setCurrency(e.target.value as Currency)}>
          {CURRENCIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <button className="primary" disabled={submitting || !name.trim()} onClick={submit}>
        Create
      </button>
    </div>
  );
}
