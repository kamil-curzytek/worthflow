import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { CHART_PALETTE, TIME_PERIODS } from "../constants";
import { formatDate, formatMoney, formatPercent, formatSignedMoney, monthsAgoIso } from "../format";
import type {
  Account,
  AllocationResponse,
  AssetClassTrendResponse,
  Currency,
  MonthlyChangesResponse,
  MonthlyContributionsResponse,
  PortfolioTrendResponse,
  PortfolioValueResponse,
} from "../types";

// "equity_compensation" -> "Equity compensation"
function humanizeAssetClass(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function OverviewPage({ currency }: { currency: Currency }) {
  const [value, setValue] = useState<PortfolioValueResponse | null>(null);
  const [trend, setTrend] = useState<PortfolioTrendResponse | null>(null);
  const [monthly, setMonthly] = useState<MonthlyChangesResponse | null>(null);
  const [allocation, setAllocation] = useState<AllocationResponse | null>(null);
  const [accountAllocation, setAccountAllocation] = useState<AllocationResponse | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [periodMonths, setPeriodMonths] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [contributions, setContributions] = useState<MonthlyContributionsResponse | null>(null);
  const [accountsPeriodMonths, setAccountsPeriodMonths] = useState<number | null>(null);
  const [accountTrends, setAccountTrends] = useState<Record<string, { date: string; value: string }[]>>(
    {},
  );
  const [classPeriodMonths, setClassPeriodMonths] = useState<number | null>(null);
  const [classTrend, setClassTrend] = useState<AssetClassTrendResponse | null>(null);

  useEffect(() => {
    api.listAccounts().then(setAccounts);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const start = periodMonths ? monthsAgoIso(periodMonths) : undefined;

    Promise.all([
      api.portfolioValue(currency),
      api.portfolioTrend(currency, start),
      api.monthlyChanges(currency),
      api.allocation(currency),
      api.allocation(currency, "account"),
      api.monthlyContributions(currency, start),
    ])
      .then(([v, t, m, a, aa, c]) => {
        if (cancelled) return;
        setValue(v);
        setTrend(t);
        setMonthly(m);
        setAllocation(a);
        setAccountAllocation(aa);
        setContributions(c);
      })
      .catch((err) => !cancelled && setError(err.message ?? "Failed to load"))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [currency, periodMonths]);

  useEffect(() => {
    if (accounts.length === 0) {
      setAccountTrends({});
      return;
    }
    let cancelled = false;
    const start = accountsPeriodMonths ? monthsAgoIso(accountsPeriodMonths) : undefined;
    Promise.all(
      accounts.map((a) =>
        api.accountTrend(a.id, currency, start).then((res) => [a.id, res.points] as const),
      ),
    ).then((entries) => {
      if (!cancelled) setAccountTrends(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [accounts, currency, accountsPeriodMonths]);

  useEffect(() => {
    let cancelled = false;
    const start = classPeriodMonths ? monthsAgoIso(classPeriodMonths) : undefined;
    api.assetClassTrend(currency, start).then((res) => {
      if (!cancelled) setClassTrend(res);
    });
    return () => {
      cancelled = true;
    };
  }, [currency, classPeriodMonths]);

  const chartData = useMemo(
    () =>
      trend?.points.map((p) => ({
        date: formatDate(p.date),
        value: Number(p.value),
      })) ?? [],
    [trend],
  );

  const accountsChartData = useMemo(() => {
    const dateSet = new Set<string>();
    Object.values(accountTrends).forEach((points) => points.forEach((p) => dateSet.add(p.date)));
    const dates = [...dateSet].sort();
    return dates.map((date) => {
      const row: Record<string, string | number> = { date: formatDate(date) };
      for (const a of accounts) {
        const point = accountTrends[a.id]?.find((p) => p.date === date);
        if (point) row[a.id] = Number(point.value);
      }
      return row;
    });
  }, [accountTrends, accounts]);

  // One row per month, one key per asset class (values always present — the
  // backend fills months where a class holds nothing with 0).
  const classChartData = useMemo(
    () =>
      classTrend?.months.map((month, i) => {
        const row: Record<string, string | number> = { date: formatDate(month) };
        for (const s of classTrend.series) row[s.asset_class] = Number(s.values[i]);
        return row;
      }) ?? [],
    [classTrend],
  );

  const hasEnoughAccountsData =Object.values(accountTrends).some((points) => points.length >= 2);

  const contributionsChartData = useMemo(() => {
    if (!contributions || contributions.rows.length === 0) {
      return { rows: [] as Record<string, string | number>[], topAccounts: [] as { id: string; name: string }[] };
    }

    const totals = new Map<string, { name: string; total: number }>();
    for (const row of contributions.rows) {
      for (const c of row.contributions) {
        const abs = Math.abs(Number(c.delta));
        const existing = totals.get(c.account_id);
        if (existing) {
          existing.total += abs;
        } else {
          totals.set(c.account_id, { name: c.account_name, total: abs });
        }
      }
    }

    const topIds = [...totals.entries()]
      .sort((a, b) => b[1].total - a[1].total)
      .slice(0, 5)
      .map(([id]) => id);
    const topAccounts = topIds.map((id) => ({ id, name: totals.get(id)!.name }));

    const recentRows = contributions.rows.slice(-12);
    const rows = recentRows.map((row) => {
      const entry: Record<string, string | number> = { date: formatDate(row.date) };
      let other = 0;
      for (const c of row.contributions) {
        const delta = Number(c.delta);
        if (topIds.includes(c.account_id)) {
          entry[c.account_id] = delta;
        } else {
          other += delta;
        }
      }
      entry["Other"] = other;
      return entry;
    });

    return { rows, topAccounts };
  }, [contributions]);

  const latestMonthly = monthly?.rows[monthly.rows.length - 1];

  if (error) {
    return <div className="card warning-list">Could not load dashboard: {error}</div>;
  }

  return (
    <div>
      <div className="stat-grid">
        <div className="card">
          <p className="card-title">Total wealth</p>
          <div className="stat-value figure">
            {value ? formatMoney(value.value, currency) : "—"}
          </div>
          <p className="stat-sub">as of {value ? formatDate(value.as_of) : "…"}</p>
        </div>
        <div className="card">
          <p className="card-title">Latest monthly change</p>
          <div
            className={`stat-value figure ${
              latestMonthly?.change_absolute && Number(latestMonthly.change_absolute) >= 0
                ? "positive"
                : "negative"
            }`}
          >
            {latestMonthly?.change_absolute
              ? formatSignedMoney(latestMonthly.change_absolute, currency)
              : "—"}
          </div>
          <p className="stat-sub">{formatPercent(latestMonthly?.change_percentage ?? null)}</p>
        </div>
        <div className="card">
          <p className="card-title">Change over period</p>
          <div
            className={`stat-value figure ${
              trend?.cumulative_growth && Number(trend.cumulative_growth.absolute) >= 0
                ? "positive"
                : "negative"
            }`}
          >
            {trend?.cumulative_growth
              ? formatSignedMoney(trend.cumulative_growth.absolute, currency)
              : "—"}
          </div>
          <p className="stat-sub">{formatPercent(trend?.cumulative_growth?.percentage ?? null)}</p>
        </div>
        <div className="card">
          <p className="card-title">Accounts</p>
          <div className="stat-value figure">{accounts.length}</div>
          <p className="stat-sub">
            {allocation?.slices.length ?? 0} asset {allocation?.slices.length === 1 ? "class" : "classes"} tracked
          </p>
        </div>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="card-title" style={{ margin: 0 }}>
            Portfolio trend
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
        {loading ? (
          <div className="empty-state">Loading…</div>
        ) : chartData.length < 2 ? (
          <div className="empty-state">
            Not enough history yet for a trend — add at least two months of data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="var(--text-muted)" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="var(--text-muted)"
                tickFormatter={(v) => formatMoney(v, currency)}
                width={90}
              />
              <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="var(--accent)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 20 }}>
        <div className="card">
          <p className="card-title">Monthly changes</p>
          {!monthly || monthly.rows.length === 0 ? (
            <div className="empty-state">No data yet.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Month</th>
                  <th className="num">Total</th>
                  <th className="num">Change</th>
                  <th className="num">Change %</th>
                </tr>
              </thead>
              <tbody>
                {[...monthly.rows]
                  .reverse()
                  .slice(0, 12)
                  .map((row) => (
                    <tr key={row.date}>
                      <td>{formatDate(row.date)}</td>
                      <td className="num">{formatMoney(row.total, currency)}</td>
                      <td
                        className={`num ${
                          row.change_absolute && Number(row.change_absolute) >= 0
                            ? "positive"
                            : "negative"
                        }`}
                      >
                        {row.change_absolute
                          ? formatSignedMoney(row.change_absolute, currency)
                          : "—"}
                      </td>
                      <td className="num">{formatPercent(row.change_percentage)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <p className="card-title">Allocation</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div>
              <p className="stat-sub" style={{ textAlign: "center" }}>
                By asset class
              </p>
              {!allocation || allocation.slices.length === 0 ? (
                <div className="empty-state">No data yet.</div>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={allocation.slices}
                      dataKey={(s) => Number(s.value)}
                      nameKey="label"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={2}
                    >
                      {allocation.slices.map((_, i) => (
                        <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />
                      ))}
                    </Pie>
                    <Legend />
                    <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
            <div>
              <p className="stat-sub" style={{ textAlign: "center" }}>
                By account
              </p>
              {!accountAllocation || accountAllocation.slices.length === 0 ? (
                <div className="empty-state">No data yet.</div>
              ) : (
                <ResponsiveContainer width="100%" height={320}>
                  <PieChart>
                    <Pie
                      data={accountAllocation.slices}
                      dataKey={(s) => Number(s.value)}
                      nameKey="label"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={2}
                    >
                      {accountAllocation.slices.map((_, i) => (
                        <Cell key={i} fill={CHART_PALETTE[i % CHART_PALETTE.length]} />
                      ))}
                    </Pie>
                    <Legend />
                    <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="card-title" style={{ margin: 0 }}>
            All accounts trend
          </p>
          <div style={{ display: "flex", gap: 4 }}>
            {TIME_PERIODS.map((p) => (
              <button
                key={p.label}
                className={accountsPeriodMonths === p.months ? "primary" : "secondary"}
                style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => setAccountsPeriodMonths(p.months)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {accounts.length === 0 ? (
          <div className="empty-state">No accounts yet.</div>
        ) : !hasEnoughAccountsData ? (
          <div className="empty-state">
            Not enough history yet for a trend — add at least two months of data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={accountsChartData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="var(--text-muted)" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="var(--text-muted)"
                tickFormatter={(v) => formatMoney(v, currency)}
                width={90}
              />
              <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
              <Legend />
              {accounts.map((a, i) => (
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

      <div className="card">
        <p className="card-title">What's driving the change</p>
        {loading ? (
          <div className="empty-state">Loading…</div>
        ) : contributionsChartData.rows.length < 1 ? (
          <div className="empty-state">No data yet.</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={contributionsChartData.rows}
              margin={{ top: 16, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="var(--text-muted)" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="var(--text-muted)"
                tickFormatter={(v) => formatMoney(v, currency)}
                width={90}
              />
              <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
              <Legend />
              <ReferenceLine y={0} stroke="var(--border)" />
              {contributionsChartData.topAccounts.map((a, i) => (
                <Bar
                  key={a.id}
                  dataKey={a.id}
                  name={a.name}
                  stackId="contrib"
                  fill={CHART_PALETTE[i % CHART_PALETTE.length]}
                />
              ))}
              <Bar dataKey="Other" name="Other" stackId="contrib" fill="var(--text-muted)" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p className="card-title" style={{ margin: 0 }}>
            Trend by asset class
          </p>
          <div style={{ display: "flex", gap: 4 }}>
            {TIME_PERIODS.map((p) => (
              <button
                key={p.label}
                className={classPeriodMonths === p.months ? "primary" : "secondary"}
                style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => setClassPeriodMonths(p.months)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {!classTrend ? (
          <div className="empty-state">Loading…</div>
        ) : classChartData.length < 2 || classTrend.series.length === 0 ? (
          <div className="empty-state">
            Not enough history yet for a trend — add at least two months of data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={classChartData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="var(--text-muted)" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="var(--text-muted)"
                tickFormatter={(v) => formatMoney(v, currency)}
                width={90}
              />
              <Tooltip formatter={(v: number) => formatMoney(v, currency)} />
              <Legend />
              {classTrend.series.map((s, i) => (
                <Line
                  key={s.asset_class}
                  type="monotone"
                  dataKey={s.asset_class}
                  name={humanizeAssetClass(s.asset_class)}
                  stroke={CHART_PALETTE[i % CHART_PALETTE.length]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
