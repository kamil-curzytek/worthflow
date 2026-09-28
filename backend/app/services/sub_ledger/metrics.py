"""Which metric rows exist per sub-ledger category, and how to display them.

Mirrors the role app/services/import_excel/mapping.py plays for accounts:
the one place that says what a row means, so renaming or adding a metric is
an edit here, not a change to the parser or the API.
"""

from __future__ import annotations

from dataclasses import dataclass

Unit = str  # "EUR" | "USD" | "PLN" | "shares" | "percent"

TRADING212 = "trading212"
ESPP = "espp"
PASSIVE_INCOME = "passive_income"


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    unit: Unit
    editable: bool = True
    """False for rows that are Excel formulas derived from other rows in the
    same sheet (e.g. RoR% = Investments/Invested amount - 1) rather than
    typed-in numbers — editing them directly wouldn't mean anything since
    they're mathematically determined by the editable rows around them."""


METRICS_BY_CATEGORY: dict[str, list[MetricDef]] = {
    TRADING212: [
        MetricDef("total", "Total", "EUR"),
        MetricDef("net_deposits", "Net deposits", "EUR"),
        MetricDef("investments", "Investments", "EUR"),
        MetricDef("invested_amount", "Invested amount", "EUR", editable=False),
        MetricDef("return", "Return", "EUR"),
        MetricDef("ror_pct", "RoR%", "percent", editable=False),
        MetricDef("ror_pct_no_dividends", "RoR% (no dividends)", "percent", editable=False),
        MetricDef("dividends_acc", "Dividends (accumulated)", "EUR", editable=False),
        MetricDef("dividends_monthly", "Dividends (monthly)", "EUR"),
        MetricDef("free_cash", "Free cash", "EUR"),
        MetricDef("cash_interest_acc", "Cash interest (accumulated)", "EUR", editable=False),
        MetricDef("cash_interest_monthly", "Cash interest (monthly)", "EUR"),
    ],
    ESPP: [
        MetricDef("deposit_eur", "Deposit", "EUR"),
        MetricDef("end_sum_usd", "End sum", "USD"),
        MetricDef("gain_loss", "Gain / loss", "USD", editable=False),
        MetricDef("stock_qty", "Stock qty", "shares"),
        MetricDef("rsu_qty", "RSU qty", "shares"),
    ],
    PASSIVE_INCOME: [
        MetricDef("pln_interest", "PLN interest", "PLN"),
        MetricDef("n26_interest", "N26 interest", "EUR"),
        MetricDef("t212_interest", "Trading212 interest", "EUR"),
        MetricDef("t212_dividends", "Trading212 dividends", "EUR"),
    ],
}


def metric_defs(category: str) -> list[MetricDef]:
    return METRICS_BY_CATEGORY[category]
