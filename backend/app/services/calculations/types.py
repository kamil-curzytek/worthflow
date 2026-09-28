from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ChangeResult:
    absolute: Decimal
    percentage: Decimal | None  # None when the previous value was 0 (undefined %)


@dataclass(frozen=True)
class TrendPoint:
    date: dt.date
    value: Decimal


@dataclass(frozen=True)
class AllocationSlice:
    label: str
    value: Decimal
    percentage: Decimal


@dataclass(frozen=True)
class AccountMonthlySeries:
    """One account's balance at each month-end, in its own native currency.

    A None entry means the account didn't exist yet as of that month — distinct
    from an explicit zero balance.
    """

    account_id: str
    account_name: str
    currency: str
    values: list[Decimal | None]


@dataclass(frozen=True)
class AssetClassSeries:
    """One asset class's total value at each month-end, in the display currency.

    Unlike AccountMonthlySeries, a month where the class holds nothing is an
    explicit Decimal(0) rather than None, so the per-month sum across all
    series always equals that month's portfolio_trend value.
    """

    asset_class: str
    values: list[Decimal]


@dataclass(frozen=True)
class AccountContribution:
    account_id: str
    account_name: str
    delta: Decimal


@dataclass(frozen=True)
class MonthlyContributionRow:
    """One month's total change, broken down by which account moved it.

    sum(c.delta for c in contributions) always equals that month's whole-
    portfolio change from /monthly-changes, since a delta is either a
    month-over-month difference in the account's converted value, or (for an
    account's first-ever snapshot) its full starting value — the same way a
    newly-appearing account's balance flows into the portfolio total.
    """

    date: dt.date
    contributions: list[AccountContribution]
