import { useEffect, useState } from "react";
import { api } from "../api/client";
import { EditableMetricGrid, type MetricRow } from "../components/EditableMetricGrid";
import { TIME_PERIODS } from "../constants";
import { monthsAgoIso } from "../format";

export function EsppPage() {
  const [months, setMonths] = useState<string[]>([]);
  const [rows, setRows] = useState<MetricRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [periodMonths, setPeriodMonths] = useState<number | null>(6);

  function load() {
    const start = periodMonths ? monthsAgoIso(periodMonths) : undefined;
    return api.subLedgerTable("espp", start).then((res) => {
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
    await api.setSubLedgerValue("espp", rowId, year, month, value);
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
      <EditableMetricGrid
        title="ESPP / RSU"
        subtitle="Mirrors the ESPP sheet's own monthly tracking — EUR deposits, USD end balance, gain/loss, and ESPP and RSU share quantities — each kept in its native unit, no conversion."
        months={months}
        rows={rows}
        loading={loading}
        onSave={handleSave}
        onReload={load}
      />
    </div>
  );
}
