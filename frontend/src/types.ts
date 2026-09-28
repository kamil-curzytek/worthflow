export type Currency = "EUR" | "USD" | "PLN";

export type AccountType =
  | "checking"
  | "savings"
  | "brokerage"
  | "cash"
  | "crypto"
  | "pension"
  | "equity_compensation"
  | "other";

export type AssetClass = "cash" | "trading" | "crypto" | "equity_compensation" | "other";

export interface Account {
  id: string;
  name: string;
  type: AccountType;
  asset_class: AssetClass;
  currency: Currency;
  institution: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Snapshot {
  id: string;
  account_id: string;
  snapshot_date: string;
  value: string;
  currency: Currency;
  source: "manual" | "import_excel" | "cli";
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrendPointDto {
  date: string;
  value: string;
}

export interface ChangeDto {
  absolute: string;
  percentage: string | null;
}

export interface PortfolioTrendResponse {
  currency: Currency;
  points: TrendPointDto[];
  cumulative_growth: ChangeDto | null;
  average_monthly_change: string | null;
  high: TrendPointDto | null;
  low: TrendPointDto | null;
}

export interface MonthlyChangeRow {
  date: string;
  total: string;
  change_absolute: string | null;
  change_percentage: string | null;
}

export interface MonthlyChangesResponse {
  currency: Currency;
  rows: MonthlyChangeRow[];
}

export interface AllocationSliceDto {
  label: string;
  value: string;
  percentage: string;
}

export interface AllocationResponse {
  currency: Currency;
  as_of: string;
  slices: AllocationSliceDto[];
}

export interface PortfolioValueResponse {
  currency: Currency;
  as_of: string;
  value: string;
}

export interface AccountMonthlySeriesDto {
  account_id: string;
  account_name: string;
  currency: Currency;
  values: (string | null)[];
}

export interface AccountsMonthlyResponse {
  months: string[];
  accounts: AccountMonthlySeriesDto[];
}

export interface AccountContributionDto {
  account_id: string;
  account_name: string;
  delta: string;
}

export interface MonthlyContributionRowDto {
  date: string;
  contributions: AccountContributionDto[];
}

export interface MonthlyContributionsResponse {
  currency: Currency;
  rows: MonthlyContributionRowDto[];
}

export interface AssetClassSeriesDto {
  asset_class: string;
  values: string[];
}

export interface AssetClassTrendResponse {
  currency: Currency;
  months: string[];
  series: AssetClassSeriesDto[];
}

export type SubLedgerCategory ="trading212" | "espp" | "passive_income";

export interface SubLedgerRowDto {
  metric: string;
  label: string;
  unit: "EUR" | "USD" | "PLN" | "shares" | "percent";
  editable: boolean;
  values: (string | null)[];
}

export interface SubLedgerTableResponse {
  category: SubLedgerCategory;
  months: string[];
  rows: SubLedgerRowDto[];
}

export interface PassiveIncomeTableResponse extends SubLedgerTableResponse {
  currency: Currency;
}

export interface PassiveIncomeTrendSeriesDto {
  metric: string;
  label: string;
  values: (string | null)[];
}

export interface PassiveIncomeTrendResponse {
  currency: Currency;
  months: string[];
  series: PassiveIncomeTrendSeriesDto[];
}

export interface ImportPreviewRowDto {
  account_name: string;
  snapshot_date: string;
  value: string;
  currency: Currency;
  is_new_account: boolean;
  is_duplicate: boolean;
  cell: string;
}

export interface ImportPreviewResponse {
  new_snapshot_count: number;
  duplicate_count: number;
  new_account_names: string[];
  warnings: string[];
  rows: ImportPreviewRowDto[];
  source_path: string;
}

export interface ImportCommitResponse {
  import_batch_id: string;
  status: string;
  row_count: number;
  notes: string | null;
}

export interface ProposedEntryDto {
  date: string;
  value: string;
}

export interface ProposedAccountDto {
  source_label: string;
  suggested_name: string;
  suggested_currency: string;
  suggested_type: string;
  suggested_asset_class: string;
  entries: ProposedEntryDto[];
}

export interface ImportInterpretationResponse {
  summary: string;
  accounts: ProposedAccountDto[];
  warnings: string[];
  source_path: string;
}

export interface AiImportCommitResponse {
  import_batch_id: string;
  status: string;
  row_count: number;
}
