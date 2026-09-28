import type { Currency } from "./types";

const LOCALE_BY_CURRENCY: Record<Currency, string> = {
  EUR: "de-DE",
  USD: "en-US",
  PLN: "pl-PL",
};

export function formatMoney(value: string | number, currency: Currency): string {
  const n = typeof value === "string" ? Number(value) : value;
  return new Intl.NumberFormat(LOCALE_BY_CURRENCY[currency], {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatPercent(value: string | number | null): string {
  if (value === null) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

export function formatSignedMoney(value: string | number, currency: Currency): string {
  const n = typeof value === "string" ? Number(value) : value;
  const sign = n > 0 ? "+" : "";
  return `${sign}${formatMoney(n, currency)}`;
}

export function formatDate(iso: string): string {
  // Always English month names — currency formatting follows the selected
  // currency's locale, but dates should read the same regardless of it.
  return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short" });
}

export function monthsAgoIso(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}
