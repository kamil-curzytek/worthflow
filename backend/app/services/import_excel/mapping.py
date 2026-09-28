"""Import mapping configuration.

The Excel file is a *source format*, not the app's data model. This module is
the single place that says "this row label in the sheet means this account,
in this currency, of this type" — so when the sheet's accounts change (one
renamed, a new one added, an old one closed), only this mapping needs an
update, not the parser or the database layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.database.models import AccountType, AssetClass


@dataclass(frozen=True)
class AccountMapping:
    excel_label: str
    account_name: str
    account_type: AccountType
    asset_class: AssetClass
    currency: str


# Known account rows in the "Raw data" sheet, and how they map onto the
# normalized domain model. Derived from the sheet's own SUM/category formulas
# (see docs/architecture.md for the full trace).
_EQUITY_COMP = AssetClass.EQUITY_COMPENSATION

DEFAULT_ACCOUNT_MAPPINGS: list[AccountMapping] = [
    AccountMapping(
        "mBank PLN account", "mBank PLN account", AccountType.CHECKING, AssetClass.CASH, "PLN"
    ),
    AccountMapping(
        "mbank PLN investment", "mBank PLN investment", AccountType.SAVINGS, AssetClass.CASH, "PLN"
    ),
    AccountMapping("velobank PLN", "Velobank PLN", AccountType.SAVINGS, AssetClass.CASH, "PLN"),
    AccountMapping("mbank EUR", "mBank EUR", AccountType.CHECKING, AssetClass.CASH, "EUR"),
    AccountMapping("Revolut", "Revolut", AccountType.CHECKING, AssetClass.CASH, "PLN"),
    AccountMapping("N26", "N26", AccountType.CHECKING, AssetClass.CASH, "EUR"),
    AccountMapping("N26 savings", "N26 savings", AccountType.SAVINGS, AssetClass.CASH, "EUR"),
    AccountMapping("BlockFi", "BlockFi", AccountType.CRYPTO, AssetClass.CRYPTO, "USD"),
    AccountMapping("Trading212", "Trading212", AccountType.BROKERAGE, AssetClass.TRADING, "EUR"),
    AccountMapping(
        "eTrade RSU", "eTrade RSU", AccountType.EQUITY_COMPENSATION, _EQUITY_COMP, "USD"
    ),
    AccountMapping(
        "eTrade ESPP", "eTrade ESPP", AccountType.EQUITY_COMPENSATION, _EQUITY_COMP, "USD"
    ),
    AccountMapping("eTrade Cash", "eTrade Cash", AccountType.CASH, AssetClass.CASH, "USD"),
    AccountMapping("Flat deposit", "Flat deposit", AccountType.CASH, AssetClass.CASH, "EUR"),
]

MAPPINGS_BY_LABEL: dict[str, AccountMapping] = {m.excel_label: m for m in DEFAULT_ACCOUNT_MAPPINGS}

# Labels the sheet uses for its own computed rollups (SUM, category totals,
# percentages, the duplicate chart-source block). These are recognized and
# skipped on purpose — they're recomputed by our own calculation engine, not
# imported as data — rather than being reported as unmapped/unknown rows.
KNOWN_DERIVED_LABELS: set[str] = {
    "SUM",
    "CASH",
    "CASH interest %",
    "TRADING",
    "CRYPTO",
    "TESLA SHARES",
    "CASH %",
    "TRADING %",
    "CRYPTO %",
    "TESLA SHARES %",
    "Total",
    "TESLA PRICE",
}


@dataclass(frozen=True)
class ExcelSheetLayout:
    sheet_name: str = "Raw data"
    year_row: int = 3
    month_row: int = 4
    label_col: str = "B"
