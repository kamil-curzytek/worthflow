import type {
  Account,
  AccountsMonthlyResponse,
  AccountType,
  AiImportCommitResponse,
  AllocationResponse,
  AssetClass,
  AssetClassTrendResponse,
  Currency,
  ImportCommitResponse,
  ImportInterpretationResponse,
  ImportPreviewResponse,
  MonthlyChangesResponse,
  MonthlyContributionsResponse,
  PassiveIncomeTableResponse,
  PassiveIncomeTrendResponse,
  PortfolioTrendResponse,
  PortfolioValueResponse,
  Snapshot,
  SubLedgerCategory,
  SubLedgerTableResponse,
} from "../types";

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/**
 * FastAPI's `detail` is a plain string for HTTPException, but a list of
 * Pydantic error objects ({type, loc, msg, ...}) for request validation
 * failures (422s) — flatten either shape into one readable string.
 */
function extractErrorMessage(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) =>
        typeof d === "object" && d !== null && "msg" in d
          ? String((d as { msg: unknown }).msg)
          : JSON.stringify(d),
      )
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(extractErrorMessage(body, response.statusText), response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  listAccounts: (includeInactive = false) =>
    request<Account[]>(`/accounts?include_inactive=${includeInactive}`),

  createAccount: (payload: {
    name: string;
    type: AccountType;
    asset_class: AssetClass;
    currency: Currency;
    institution?: string;
  }) => request<Account>("/accounts", { method: "POST", body: JSON.stringify(payload) }),

  deactivateAccount: (accountId: string) =>
    request<Account>(`/accounts/${accountId}/deactivate`, { method: "POST" }),

  activateAccount: (accountId: string) =>
    request<Account>(`/accounts/${accountId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: true }),
    }),

  listSnapshots: (accountId?: string) =>
    request<Snapshot[]>(`/snapshots${accountId ? `?account_id=${accountId}` : ""}`),

  createSnapshot: (payload: {
    account_id: string;
    snapshot_date: string;
    value: string;
    note?: string;
  }) => request<Snapshot>("/snapshots", { method: "POST", body: JSON.stringify(payload) }),

  updateSnapshot: (snapshotId: string, payload: { value?: string; note?: string }) =>
    request<Snapshot>(`/snapshots/${snapshotId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  setMonthlyValue: (accountId: string, year: number, month: number, value: string) =>
    request<Snapshot>("/snapshots/monthly", {
      method: "PUT",
      body: JSON.stringify({ account_id: accountId, year, month, value }),
    }),

  deleteSnapshot: (snapshotId: string) =>
    request<void>(`/snapshots/${snapshotId}`, { method: "DELETE" }),

  portfolioValue: (currency: Currency, asOf?: string) =>
    request<PortfolioValueResponse>(
      `/portfolio/value?currency=${currency}${asOf ? `&as_of=${asOf}` : ""}`,
    ),

  portfolioTrend: (currency: Currency, start?: string, end?: string) =>
    request<PortfolioTrendResponse>(
      `/portfolio/trend?currency=${currency}${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`,
    ),

  monthlyChanges: (currency: Currency) =>
    request<MonthlyChangesResponse>(`/portfolio/monthly-changes?currency=${currency}`),

  monthlyContributions: (currency: Currency, start?: string, end?: string) =>
    request<MonthlyContributionsResponse>(
      `/portfolio/monthly-contributions?currency=${currency}${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`,
    ),

  accountsMonthly: (start?: string, end?: string) =>
    request<AccountsMonthlyResponse>(
      `/portfolio/accounts-monthly?${start ? `start=${start}&` : ""}${end ? `end=${end}` : ""}`,
    ),

  allocation: (currency: Currency, by: "asset_class" | "currency" | "account" = "asset_class") =>
    request<AllocationResponse>(`/portfolio/allocation?currency=${currency}&by=${by}`),

  assetClassTrend: (currency: Currency, start?: string, end?: string) =>
    request<AssetClassTrendResponse>(
      `/portfolio/asset-class-trend?currency=${currency}${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`,
    ),

  accountTrend: (accountId: string, currency: Currency, start?: string) =>
    request<PortfolioTrendResponse>(
      `/portfolio/accounts/${accountId}/trend?currency=${currency}${start ? `&start=${start}` : ""}`,
    ),

  currencies: () => request<{ currencies: Currency[] }>("/currencies"),

  subLedgerTable: (category: "trading212" | "espp", start?: string, end?: string) =>
    request<SubLedgerTableResponse>(
      `/sub-ledger/${category}?${start ? `start=${start}&` : ""}${end ? `end=${end}` : ""}`,
    ),

  passiveIncomeTable: (currency: Currency, start?: string, end?: string) =>
    request<PassiveIncomeTableResponse>(
      `/sub-ledger/passive-income?currency=${currency}${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`,
    ),

  passiveIncomeTrend: (currency: Currency, start?: string, end?: string) =>
    request<PassiveIncomeTrendResponse>(
      `/sub-ledger/passive-income/trend?currency=${currency}${start ? `&start=${start}` : ""}${end ? `&end=${end}` : ""}`,
    ),

  setSubLedgerValue: (
    category: SubLedgerCategory,
    metric: string,
    year: number,
    month: number,
    value: string,
  ) =>
    request<{ category: string; metric: string; date: string; value: string }>(
      `/sub-ledger/${category}/monthly`,
      { method: "PUT", body: JSON.stringify({ metric, year, month, value }) },
    ),

  previewImport: async (file: File): Promise<ImportPreviewResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/imports/preview", { method: "POST", body: formData });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(extractErrorMessage(body, response.statusText), response.status);
    }
    return response.json();
  },

  commitImport: (sourcePath: string, overwriteDuplicates: boolean) =>
    request<ImportCommitResponse>(
      `/imports/commit?source_path=${encodeURIComponent(sourcePath)}&overwrite_duplicates=${overwriteDuplicates}`,
      { method: "POST" },
    ),

  aiPreviewImport: async (file: File): Promise<ImportInterpretationResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/imports/ai-preview", { method: "POST", body: formData });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(extractErrorMessage(body, response.statusText), response.status);
    }
    return response.json();
  },

  aiCommitImport: (accounts: AiAccountCommitPayload[]) =>
    request<AiImportCommitResponse>("/imports/ai-commit", {
      method: "POST",
      body: JSON.stringify({ accounts }),
    }),
};

export interface AiEntryCommitPayload {
  date: string;
  value: string;
  include: boolean;
}

export interface AiAccountCommitPayload {
  name: string;
  currency: Currency;
  type: AccountType;
  asset_class: AssetClass;
  include: boolean;
  entries: AiEntryCommitPayload[];
}

export { ApiError };
