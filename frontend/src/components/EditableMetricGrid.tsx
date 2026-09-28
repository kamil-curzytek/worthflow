import { useMemo, useState } from "react";
import { ApiError } from "../api/client";
import { formatDate } from "../format";
import type { Currency } from "../types";

const DECIMAL_PATTERN = /^-?\d+(\.\d+)?$/;

export type MetricUnit = "EUR" | "USD" | "PLN" | "shares" | "percent";

export interface MetricRow {
  id: string;
  label: string;
  unit: MetricUnit;
  editable: boolean;
  values: (string | null)[];
}

interface PendingChange {
  rowId: string;
  rowLabel: string;
  monthIso: string;
  unit: MetricUnit;
  oldValue: string | null;
  newValue: string;
}

function changeKey(rowId: string, monthIso: string): string {
  return `${rowId}::${monthIso}`;
}

function formatValue(value: string, unit: MetricUnit): string {
  const n = Number(value);
  if (unit === "shares") return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (unit === "percent") return `${n.toFixed(2)}%`;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: unit as Currency,
    maximumFractionDigits: 2,
  }).format(n);
}

export function EditableMetricGrid({
  title,
  subtitle,
  months,
  rows,
  loading,
  onSave,
  onReload,
}: {
  title: string;
  subtitle?: string;
  months: string[];
  rows: MetricRow[];
  loading: boolean;
  onSave: (rowId: string, monthIso: string, value: string) => Promise<void>;
  onReload: () => void | Promise<void>;
}) {
  const [editingEnabled, setEditingEnabled] = useState(false);
  const [pending, setPending] = useState<Record<string, PendingChange>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pendingList = useMemo(() => Object.values(pending), [pending]);

  function stageChange(change: PendingChange) {
    setPending((prev) => ({ ...prev, [changeKey(change.rowId, change.monthIso)]: change }));
  }

  function discardChange(key: string) {
    setPending((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function discardAll() {
    setPending({});
  }

  function toggleEditing() {
    if (editingEnabled && pendingList.length > 0) {
      const ok = window.confirm(
        `You have ${pendingList.length} unsaved change(s). Turning off editing will discard ` +
          "them. Continue?",
      );
      if (!ok) return;
      discardAll();
    }
    setEditingEnabled((v) => !v);
  }

  async function saveAll() {
    setSaving(true);
    setError(null);
    const failures: string[] = [];
    for (const change of pendingList) {
      try {
        await onSave(change.rowId, change.monthIso, change.newValue);
        discardChange(changeKey(change.rowId, change.monthIso));
      } catch (err) {
        failures.push(
          `${change.rowLabel} (${formatDate(change.monthIso)}): ` +
            (err instanceof ApiError ? err.message : "failed to save"),
        );
      }
    }
    if (failures.length > 0) {
      setError(`${failures.length} change(s) could not be saved:\n${failures.join("\n")}`);
    }
    await onReload();
    setSaving(false);
  }

  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <p className="card-title" style={{ margin: 0 }}>
            {title}
          </p>
          {subtitle && (
            <p className="stat-sub" style={{ margin: "4px 0 0" }}>
              {subtitle}
            </p>
          )}
        </div>
        <button className={editingEnabled ? "primary" : "secondary"} onClick={toggleEditing}>
          {editingEnabled ? "🔓 Editing enabled" : "🔒 Enable editing"}
        </button>
      </div>

      {editingEnabled && (
        <div className="demo-banner" style={{ marginTop: 12 }}>
          Editing is on — click any value to change it. Changes are staged below and only written
          to the database when you click "Save changes".
        </div>
      )}
      {error && (
        <div className="warning-list" style={{ whiteSpace: "pre-line" }}>
          {error}
        </div>
      )}

      {editingEnabled && pendingList.length > 0 && (
        <div
          className="card"
          style={{ marginTop: 12, background: "color-mix(in srgb, var(--accent) 6%, var(--surface))" }}
        >
          <p className="card-title" style={{ margin: "0 0 8px" }}>
            {pendingList.length} unsaved change{pendingList.length === 1 ? "" : "s"}
          </p>
          <table>
            <tbody>
              {pendingList.map((c) => {
                const key = changeKey(c.rowId, c.monthIso);
                return (
                  <tr key={key}>
                    <td>{c.rowLabel}</td>
                    <td>{formatDate(c.monthIso)}</td>
                    <td className="num" style={{ color: "var(--text-muted)" }}>
                      {c.oldValue !== null ? formatValue(c.oldValue, c.unit) : "—"}
                    </td>
                    <td className="num">→</td>
                    <td className="num">{formatValue(c.newValue, c.unit)}</td>
                    <td>
                      <button
                        className="secondary"
                        style={{ padding: "2px 8px", fontSize: 12 }}
                        onClick={() => discardChange(key)}
                      >
                        Discard
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="form-row" style={{ marginTop: 12 }}>
            <button className="primary" disabled={saving} onClick={saveAll}>
              {saving ? "Saving…" : `Save ${pendingList.length} change(s)`}
            </button>
            <button className="secondary" disabled={saving} onClick={discardAll}>
              Discard all
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="empty-state">Loading…</div>
      ) : rows.length === 0 || months.length === 0 ? (
        <div className="empty-state">No data yet.</div>
      ) : (
        <div className="table-scroll" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th className="sticky-col">Metric</th>
                {months.map((m) => (
                  <th key={m} className="num">
                    {formatDate(m)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={row.editable ? undefined : "row-computed"}>
                  <td className="sticky-col">
                    {row.label}{" "}
                    <span className="stat-sub" style={{ fontSize: 11 }}>
                      {row.unit !== "shares" && row.unit !== "percent" ? row.unit : ""}
                    </span>
                    {!row.editable && <span className="row-computed-badge"> (computed)</span>}
                  </td>
                  {row.values.map((v, i) => {
                    const monthIso = months[i];
                    const key = changeKey(row.id, monthIso);
                    const change = pending[key];
                    return (
                      <td key={i} className="num">
                        {editingEnabled && row.editable ? (
                          <EditableCell
                            value={change ? change.newValue : v}
                            pending={Boolean(change)}
                            unit={row.unit}
                            onCommit={(newValue) =>
                              stageChange({
                                rowId: row.id,
                                rowLabel: row.label,
                                monthIso,
                                unit: row.unit,
                                oldValue: v,
                                newValue,
                              })
                            }
                          />
                        ) : (
                          <span className={v === null ? "cell-readonly-empty" : undefined}>
                            {v !== null ? formatValue(v, row.unit) : "—"}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function EditableCell({
  value,
  pending,
  unit,
  onCommit,
}: {
  value: string | null;
  pending: boolean;
  unit: MetricUnit;
  onCommit: (value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [invalid, setInvalid] = useState(false);

  function startEditing() {
    setDraft(value ?? "");
    setInvalid(false);
    setEditing(true);
  }

  function commit() {
    const trimmed = draft.trim();
    if (trimmed === "" || trimmed === (value ?? "")) {
      setEditing(false);
      return;
    }
    if (!DECIMAL_PATTERN.test(trimmed)) {
      setInvalid(true);
      return; // keep editing so the user can fix it
    }
    setInvalid(false);
    onCommit(trimmed);
    setEditing(false);
  }

  if (editing) {
    return (
      <div style={{ position: "relative" }}>
        <input
          autoFocus
          className="cell-input"
          value={draft}
          inputMode="decimal"
          onChange={(e) => {
            setDraft(e.target.value);
            setInvalid(false);
          }}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") {
              setDraft(value ?? "");
              setInvalid(false);
              setEditing(false);
            }
          }}
        />
        {invalid && <div className="cell-error">Enter a number, e.g. 1234.56</div>}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={pending ? "cell-value cell-value-pending" : "cell-value"}
      onClick={startEditing}
    >
      {value !== null ? formatValue(value, unit) : <span className="cell-empty">+ add</span>}
    </button>
  );
}
