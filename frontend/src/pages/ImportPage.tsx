import { Fragment, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AiAccountCommitPayload } from "../api/client";
import { formatMoney } from "../format";
import type {
  AccountType,
  AssetClass,
  Currency,
  ImportInterpretationResponse,
  ImportPreviewResponse,
  ProposedAccountDto,
} from "../types";

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

interface ReviewAccount {
  source_label: string;
  name: string;
  currency: Currency;
  type: AccountType;
  asset_class: AssetClass;
  include: boolean;
  expanded: boolean;
  entries: { date: string; value: string }[];
}

function toReviewAccount(a: ProposedAccountDto): ReviewAccount {
  return {
    source_label: a.source_label,
    name: a.suggested_name,
    currency: (CURRENCIES.includes(a.suggested_currency as Currency)
      ? a.suggested_currency
      : "EUR") as Currency,
    type: (ACCOUNT_TYPES.includes(a.suggested_type as AccountType)
      ? a.suggested_type
      : "other") as AccountType,
    asset_class: (ASSET_CLASSES.includes(a.suggested_asset_class as AssetClass)
      ? a.suggested_asset_class
      : "other") as AssetClass,
    include: a.entries.length > 0,
    expanded: false,
    entries: a.entries,
  };
}

export function ImportPage() {
  return (
    <div>
      <AiImportSection />
      <QuickExcelImportSection />
    </div>
  );
}

function AiImportSection() {
  const [interpretation, setInterpretation] = useState<ImportInterpretationResponse | null>(null);
  const [reviewAccounts, setReviewAccounts] = useState<ReviewAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function handleFile(file: File) {
    setLoading(true);
    setError(null);
    setNotConfigured(null);
    setResult(null);
    setInterpretation(null);
    try {
      const res = await api.aiPreviewImport(file);
      setInterpretation(res);
      setReviewAccounts(res.accounts.map(toReviewAccount));
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setNotConfigured(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to read file");
      }
    } finally {
      setLoading(false);
    }
  }

  function updateAccount(index: number, patch: Partial<ReviewAccount>) {
    setReviewAccounts((prev) => prev.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  }

  async function confirmImport() {
    setLoading(true);
    setError(null);
    try {
      const payload: AiAccountCommitPayload[] = reviewAccounts.map((a) => ({
        name: a.name,
        currency: a.currency,
        type: a.type,
        asset_class: a.asset_class,
        include: a.include,
        entries: a.entries.map((e) => ({ date: e.date, value: e.value, include: a.include })),
      }));
      const res = await api.aiCommitImport(payload);
      setResult(`Imported ${res.row_count} values.`);
      setInterpretation(null);
      setReviewAccounts([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  const includedCount = reviewAccounts.filter((a) => a.include).length;

  return (
    <div className="card">
      <p className="card-title">AI-assisted import</p>
      <p className="stat-sub">
        Upload any spreadsheet or CSV of account balances. An AI reads the file and proposes a
        mapping — nothing is saved until you review and confirm it below.
      </p>
      <div className="form-row" style={{ marginTop: 12 }}>
        <input
          type="file"
          accept=".xlsx,.xlsm,.csv"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </div>

      {loading && <div className="empty-state">Working…</div>}
      {error && <div className="warning-list">{error}</div>}
      {result && (
        <div className="card" style={{ background: "transparent" }}>
          {result}
        </div>
      )}

      {notConfigured && (
        <div className="warning-list">
          <strong>AI-assisted import isn't enabled.</strong>
          <p style={{ margin: "6px 0 0" }}>{notConfigured}</p>
        </div>
      )}

      {interpretation && (
        <div style={{ marginTop: 16 }}>
          <p className="stat-sub">{interpretation.summary}</p>

          {interpretation.warnings.length > 0 && (
            <div className="warning-list">
              <strong>{interpretation.warnings.length} note(s) from the AI:</strong>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {interpretation.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {reviewAccounts.length === 0 ? (
            <div className="empty-state">No accounts found in this file.</div>
          ) : (
            <table style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th />
                  <th>Found as</th>
                  <th>Name</th>
                  <th>Currency</th>
                  <th>Type</th>
                  <th>Asset class</th>
                  <th>Entries</th>
                </tr>
              </thead>
              <tbody>
                {reviewAccounts.map((a, i) => (
                  <Fragment key={a.source_label + i}>
                    <tr>
                      <td>
                        <input
                          type="checkbox"
                          checked={a.include}
                          onChange={(e) => updateAccount(i, { include: e.target.checked })}
                        />
                      </td>
                      <td>{a.source_label}</td>
                      <td>
                        <input
                          value={a.name}
                          onChange={(e) => updateAccount(i, { name: e.target.value })}
                          style={{ width: 140 }}
                        />
                      </td>
                      <td>{a.currency}</td>
                      <td>
                        <select
                          value={a.type}
                          onChange={(e) => updateAccount(i, { type: e.target.value as AccountType })}
                        >
                          {ACCOUNT_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          value={a.asset_class}
                          onChange={(e) =>
                            updateAccount(i, { asset_class: e.target.value as AssetClass })
                          }
                        >
                          {ASSET_CLASSES.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <button
                          className="secondary"
                          style={{ padding: "4px 10px", fontSize: 12 }}
                          onClick={() => updateAccount(i, { expanded: !a.expanded })}
                        >
                          {a.entries.length} {a.expanded ? "▲" : "▼"}
                        </button>
                      </td>
                    </tr>
                    {a.expanded && (
                      <tr>
                        <td />
                        <td colSpan={6}>
                          <div style={{ maxHeight: 160, overflowY: "auto" }}>
                            <table>
                              <tbody>
                                {a.entries.map((e, j) => (
                                  <tr key={j}>
                                    <td>{e.date}</td>
                                    <td className="num">{formatMoney(e.value, a.currency)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}

          <div className="form-row" style={{ marginTop: 16 }}>
            <button
              className="primary"
              disabled={loading || includedCount === 0}
              onClick={confirmImport}
            >
              Confirm and import {includedCount} account(s)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function QuickExcelImportSection() {
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function handleFile(file: File) {
    setLoading(true);
    setError(null);
    setResult(null);
    setPreview(null);
    try {
      const p = await api.previewImport(file);
      setPreview(p);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to read file");
    } finally {
      setLoading(false);
    }
  }

  async function confirmImport() {
    if (!preview) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.commitImport(preview.source_path, overwrite);
      setResult(`Imported ${res.row_count} snapshots.`);
      setPreview(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p className="card-title" style={{ margin: 0 }}>
          Quick import (exact "Raw data" layout)
        </p>
      </div>
      <p className="stat-sub" style={{ margin: "4px 0 0" }}>
        Free, instant, no AI required — but only understands the exact accounts-as-rows,
        months-as-columns "Raw data" sheet layout. Use AI-assisted import above for anything else.
      </p>
      <>
        <div className="form-row" style={{ marginTop: 12 }}>
            <input
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
          </div>
          {loading && <div className="empty-state">Working…</div>}
          {error && <div className="warning-list">{error}</div>}
          {result && (
            <div className="card" style={{ background: "transparent" }}>
              {result}
            </div>
          )}

          {preview && (
            <div style={{ marginTop: 12 }}>
              <div className="stat-grid" style={{ marginBottom: 16 }}>
                <div>
                  <div className="stat-value figure">{preview.new_snapshot_count}</div>
                  <p className="stat-sub">new snapshots</p>
                </div>
                <div>
                  <div className="stat-value figure">{preview.duplicate_count}</div>
                  <p className="stat-sub">already imported</p>
                </div>
                <div>
                  <div className="stat-value figure">{preview.new_account_names.length}</div>
                  <p className="stat-sub">new accounts</p>
                </div>
              </div>

              {preview.new_account_names.length > 0 && (
                <p className="stat-sub">New accounts: {preview.new_account_names.join(", ")}</p>
              )}

              {preview.warnings.length > 0 && (
                <div className="warning-list">
                  <strong>{preview.warnings.length} warning(s):</strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {preview.warnings.slice(0, 20).map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{ maxHeight: 300, overflowY: "auto", marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Account</th>
                      <th>Date</th>
                      <th className="num">Value</th>
                      <th>Currency</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, 200).map((r, i) => (
                      <tr key={i}>
                        <td>{r.account_name}</td>
                        <td>{r.snapshot_date}</td>
                        <td className="num">{r.value}</td>
                        <td>{r.currency}</td>
                        <td>
                          {r.is_duplicate ? "duplicate" : r.is_new_account ? "new account" : "new"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="form-row" style={{ marginTop: 16 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={overwrite}
                    onChange={(e) => setOverwrite(e.target.checked)}
                  />
                  Overwrite duplicates with values from this file
                </label>
                <button className="primary" disabled={loading} onClick={confirmImport}>
                  Confirm import
                </button>
              </div>
            </div>
          )}
      </>
    </div>
  );
}
