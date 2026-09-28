import { useEffect, useState } from "react";
import {
  CartesianGrid,
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

type ChartUnit = "eur" | "pct";

// One small chart per metric — kept separate because the scales differ by
// orders of magnitude (Total vs. accumulated dividends vs. a percentage).
const TREND_CHARTS: { id: string; unit: ChartUnit }[] = [
  { id: "total", unit: "eur" },
  { id: "ror_pct_no_dividends", unit: "pct" },
  { id: "dividends_acc", unit: "eur" },
  { id: "cash_interest_acc", unit: "eur" },
];

// en-US compact ("€12.3K") for axis ticks — de-DE's compact form doesn't
// abbreviate thousands, which defeats the point on a narrow axis.
const compactEur = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "EUR",
  notation: "compact",
  maximumFractionDigits: 1,
});

function formatValue(value: number, unit: ChartUnit): string {
  return unit === "pct" ? `${value.toFixed(2)}%` : formatMoney(value, "EUR");
}

function formatTick(value: number, unit: ChartUnit): string {
  return unit === "pct" ? `${value}%` : compactEur.format(value);
}

function shortMonth(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export function Trading212Page() {
  const [months, setMonths] = useState<string[]>([]);
  const [rows, setRows] = useState<MetricRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [periodMonths, setPeriodMonths] = useState<number | null>(6);

  function load() {
    const start = periodMonths ? monthsAgoIso(periodMonths) : undefined;
    return api.subLedgerTable("trading212", start).then((res) => {
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
  }, [periodMonths]);

  async function handleSave(rowId: string, monthIso: string, value: string) {
    const [year, month] = monthIso.split("-").map(Number);
    await api.setSubLedgerValue("trading212", rowId, year, month, value);
  }

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
      {!loading && months.length > 0 && <TrendCharts months={months} rows={rows} />}
      <EditableMetricGrid
        title="Trading212"
        subtitle="Mirrors the Trading212 sheet's own monthly metrics — net deposits, return, dividends, cash interest, and the like — tracked directly in EUR."
        months={months}
        rows={rows}
        loading={loading}
        onSave={handleSave}
        onReload={load}
      />
    </div>
  );
}

function TrendCharts({ months, rows }: { months: string[]; rows: MetricRow[] }) {
  // Built from the already-loaded table, so the charts follow the period selector.
  const charts = TREND_CHARTS.flatMap((chart, i) => {
    const row = rows.find((r) => r.id === chart.id);
    if (!row || row.values.every((v) => v === null)) return [];
    const data = months.map((month, j) => {
      const raw = row.values[j];
      return { month, value: raw == null ? null : Number(raw) };
    });
    return [{ ...chart, label: row.label, data, color: CHART_PALETTE[i % CHART_PALETTE.length] }];
  });

  if (charts.length === 0) return null;

  return (
    <div className="card">
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 20,
        }}
      >
        {charts.map((c) => (
          <MiniTrendChart key={c.id} {...c} />
        ))}
      </div>
    </div>
  );
}

function MiniTrendChart({
  label,
  unit,
  data,
  color,
}: {
  label: string;
  unit: ChartUnit;
  data: { month: string; value: number | null }[];
  color: string;
}) {
  const latest = [...data].reverse().find((d) => d.value !== null)?.value ?? null;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <p className="card-title" style={{ margin: 0 }}>
          {label}
        </p>
        {latest !== null && (
          <span className="stat-sub" style={{ margin: 0, fontVariantNumeric: "tabular-nums" }}>
            {formatValue(latest, unit)}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11 }}
            stroke="var(--text-muted)"
            tickFormatter={(v) => shortMonth(String(v))}
          />
          <YAxis
            tick={{ fontSize: 11 }}
            stroke="var(--text-muted)"
            tickFormatter={(v) => formatTick(Number(v), unit)}
            domain={["auto", "auto"]}
            width={60}
          />
          <Tooltip
            formatter={(v: number) => formatValue(v, unit)}
            labelFormatter={(l) => formatDate(String(l))}
          />
          <Line
            type="monotone"
            dataKey="value"
            name={label}
            stroke={color}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
