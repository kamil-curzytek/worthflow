import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import { TIME_PERIODS } from "../constants";
import {
  formatDate,
  formatMoney,
  formatPercent,
  formatSignedMoney,
  monthsAgoIso,
} from "../format";
import type { AccountsMonthlyResponse, Currency, MonthlyChangesResponse } from "../types";

const DECIMAL_PATTERN = /^-?\d+(\.\d+)?$/;

interface PendingChange {
  accountId: string;
  accountName: string;
  monthIso: string;
  currency: Currency;
  oldValue: string | null;
  newValue: string;
}

function changeKey(accountId: string, monthIso: string): string {
  return `${accountId}::${monthIso}`;
}

export function MonthlyValuesPage({ currency }: { currency: Currency }) {
  const [data, setData] = useState<AccountsMonthlyResponse | null>(null);
  const [periodMonths, setPeriodMonths] = useState<number | null>(6);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingEnabled, setEditingEnabled] = useState(false);
  const [pending, setPending] = useState<Record<string, PendingChange>>({});

  const [summary, setSummary] = useState<MonthlyChangesResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const pendingList = useMemo(() => Object.values(pending), [pending]);

  function load() {
    const start = periodMonths ? monthsAgoIso(periodMonths) : undefined;
    return api.accountsMonthly(start).then(setData);
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

  useEffect(() => {
    let cancelled = false;
    setSummaryLoading(true);
    api
      .monthlyChanges(currency)
      .then((res) => !cancelled && setSummary(res))
      .catch(() => {})
      .finally(() => !cancelled && setSummaryLoading(false));
    return () => {
      cancelled = true;
    };
  }, [currency]);

  function stageChange(change: PendingChange) {
    setPending((prev) => ({ ...prev, [changeKey(change.accountId, change.monthIso)]: change }));
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
      const [year, month] = change.monthIso.split("-").map(Number);
      try {
        await api.setMonthlyValue(change.accountId, year, month, change.newValue);
        discardChange(changeKey(change.accountId, change.monthIso));
      } catch (err) {
        failures.push(
          `${change.accountName} (${formatDate(change.monthIso)}): ` +
            (err instanceof ApiError ? err.message : "failed to save"),
        );
      }
    }
    if (failures.length > 0) {
      setError(`${failures.length} change(s) could not be saved:\n${failures.join("\n")}`);
    }
    await load();
    setSaving(false);
  }

  return (
    <div>
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
              Monthly values
            </p>
            <p className="stat-sub" style={{ margin: "4px 0 0" }}>
              Each account's own currency — like the original spreadsheet, no conversion.
            </p>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
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
            <button className={editingEnabled ? "primary" : "secondary"} onClick={toggleEditing}>
              {editingEnabled ? "🔓 Editing enabled" : "🔒 Enable editing"}
            </button>
          </div>
        </div>

        {editingEnabled && (
          <div className="demo-banner" style={{ marginTop: 12 }}>
            Editing is on — click any value to change it. Changes are staged below and only
            written to the database when you click "Save changes".
          </div>
        )}
        {error && (
          <div className="warning-list" style={{ whiteSpace: "pre-line" }}>
            {error}
          </div>
        )}

        {editingEnabled && pendingList.length > 0 && (
          <div className="card" style={{ marginTop: 12, background: "color-mix(in srgb, var(--accent) 6%, var(--surface))" }}>
            <p className="card-title" style={{ margin: "0 0 8px" }}>
              {pendingList.length} unsaved change{pendingList.length === 1 ? "" : "s"}
            </p>
            <table>
              <tbody>
                {pendingList.map((c) => {
                  const key = changeKey(c.accountId, c.monthIso);
                  return (
                    <tr key={key}>
                      <td>{c.accountName}</td>
                      <td>{formatDate(c.monthIso)}</td>
                      <td className="num" style={{ color: "var(--text-muted)" }}>
                        {c.oldValue !== null ? formatMoney(c.oldValue, c.currency) : "—"}
                      </td>
                      <td className="num">→</td>
                      <td className="num">{formatMoney(c.newValue, c.currency)}</td>
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
        ) : !data || data.accounts.length === 0 ? (
          <div className="empty-state">No data yet. Import your data or add an account first.</div>
        ) : (
          <div className="table-scroll" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th className="sticky-col">Account</th>
                  {data.months.map((m) => (
                    <th key={m} className="num">
                      {formatDate(m)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.accounts.map((row) => (
                  <tr key={row.account_id}>
                    <td className="sticky-col">
                      {row.account_name}{" "}
                      <span className="stat-sub" style={{ fontSize: 11 }}>
                        {row.currency}
                      </span>
                    </td>
                    {row.values.map((v, i) => {
                      const monthIso = data.months[i];
                      const key = changeKey(row.account_id, monthIso);
                      const change = pending[key];
                      return (
                        <td key={i} className="num">
                          {editingEnabled ? (
                            <EditableCell
                              value={change ? change.newValue : v}
                              pending={Boolean(change)}
                              currency={row.currency}
                              onCommit={(newValue) =>
                                stageChange({
                                  accountId: row.account_id,
                                  accountName: row.account_name,
                                  monthIso,
                                  currency: row.currency,
                                  oldValue: v,
                                  newValue,
                                })
                              }
                            />
                          ) : (
                            <span className={v === null ? "cell-readonly-empty" : undefined}>
                              {v !== null ? formatMoney(v, row.currency) : "—"}
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

      <div className="card">
        <p className="card-title" style={{ margin: 0 }}>
          Total value by month
        </p>
        {summaryLoading ? (
          <div className="empty-state">Loading…</div>
        ) : !summary || summary.rows.length === 0 ? (
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
              {[...summary.rows].reverse().map((row) => (
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
    </div>
  );
}

function EditableCell({
  value,
  pending,
  currency,
  onCommit,
}: {
  value: string | null;
  pending: boolean;
  currency: Currency;
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
      {value !== null ? formatMoney(value, currency) : <span className="cell-empty">+ add</span>}
    </button>
  );
}
