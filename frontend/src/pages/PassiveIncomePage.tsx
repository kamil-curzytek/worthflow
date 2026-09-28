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
import { api } from "../api/client";
import { EditableMetricGrid, type MetricRow } from "../components/EditableMetricGrid";
import { CHART_PALETTE, TIME_PERIODS } from "../constants";
import { formatDate, formatMoney, monthsAgoIso } from "../format";
import type { Currency, PassiveIncomeTrendResponse } from "../types";

export function PassiveIncomePage({ currency }: { currency: Currency }) {
  const [months, setMonths] = useState<string[]>([]);
  const [rows, setRows] = useState<MetricRow[]>([]);
  const [trend, setTrend] = useState<PassiveIncomeTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [periodMonths, setPeriodMonths] = useState<number | null>(6);

  function load() {
    const start = periodMonths ? monthsAgoIso(periodMonths) : undefined;
    return Promise.all([
      api.passiveIncomeTable(currency, start),
      api.passiveIncomeTrend(currency, start),
    ]).then(([res, trendRes]) => {
      setMonths(res.months);
      setRows(
        res.rows.map((r) => ({
          id: r.metric,
          label: r.label,
          unit: r.unit,
          editable: r.editable,
          values: r.values,
        })),
      );
      setTrend(trendRes);
    });
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    load()
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currency, periodMonths]);

  async function handleSave(rowId: string, monthIso: string, value: string) {
    const [year, month] = monthIso.split("-").map(Number);
    await api.setSubLedgerValue("passive_income", rowId, year, month, value);
  }

  const trendChartData = useMemo(() => {
    if (!trend) return [];
    return trend.months.map((m, i) => {
      const row: Record<string, string | number> = { date: formatDate(m) };
      for (const s of trend.series) {
        const v = s.values[i];
        if (v !== null && v !== undefined) row[s.metric] = Number(v);
      }
      return row;
    });
  }, [trend]);

  const trendCurrency = trend?.currency ?? currency;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 4, marginBottom: 8 }}>
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
      <div className="card">
        <p className="card-title">Passive income trend</p>
        {loading && !trend ? (
          <div className="empty-state">Loading…</div>
        ) : trendChartData.length < 2 ? (
          <div className="empty-state">
            Not enough history yet for a trend — add at least two months of data.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trendChartData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="var(--text-muted)" />
              <YAxis
                tick={{ fontSize: 12 }}
                stroke="var(--text-muted)"
                tickFormatter={(v) => formatMoney(v, trendCurrency)}
                width={90}
              />
              <Tooltip formatter={(v: number) => formatMoney(v, trendCurrency)} />
              <Legend />
              {trend?.series.map((s, i) => {
                const isTotal = s.metric === "total";
                return (
                  <Line
                    key={s.metric}
                    type="monotone"
                    dataKey={s.metric}
                    name={s.label}
                    stroke={CHART_PALETTE[i % CHART_PALETTE.length]}
                    strokeWidth={isTotal ? 3.5 : 1.5}
                    dot={isTotal ? { r: 3 } : false}
                    connectNulls
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <EditableMetricGrid
        title="Passive income"
        subtitle="Mirrors the Passive income sheet's per-source tracking — PLN interest, N26 interest, and Trading212 interest and dividends — plus a total and gain recomputed using real historical exchange rates instead of the spreadsheet's static rate."
        months={months}
        rows={rows}
        loading={loading}
        onSave={handleSave}
        onReload={load}
      />
    </div>
  );
}
