"""Portfolio-level aggregation: turns snapshots (native currency, per account)
into totals and trends in the user's chosen display currency.

Conversion happens here, at read time, from the original stored value — the
original value and currency in the database are never overwritten.
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Account, Snapshot
from app.services.calculations.types import (
    AccountContribution,
    AccountMonthlySeries,
    AllocationSlice,
    AssetClassSeries,
    MonthlyContributionRow,
    TrendPoint,
)
from app.services.exchange_rates.service import ExchangeRateService


def account_balance_as_of(db: Session, account_id: str, as_of: dt.date) -> Snapshot | None:
    """The most recent snapshot for this account on or before as_of."""
    stmt = (
        select(Snapshot)
        .where(Snapshot.account_id == account_id, Snapshot.snapshot_date <= as_of)
        .order_by(Snapshot.snapshot_date.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def convert_snapshot(
    snapshot: Snapshot, target_currency: str, fx: ExchangeRateService
) -> Decimal:
    return fx.convert(
        Decimal(snapshot.value), snapshot.currency, target_currency, snapshot.snapshot_date
    )


def portfolio_value_as_of(
    db: Session,
    fx: ExchangeRateService,
    target_currency: str,
    as_of: dt.date,
    accounts: list[Account] | None = None,
) -> Decimal:
    if accounts is None:
        accounts = list(db.scalars(select(Account)))

    total = Decimal(0)
    for account in accounts:
        snapshot = account_balance_as_of(db, account.id, as_of)
        if snapshot is None:
            continue
        total += convert_snapshot(snapshot, target_currency, fx)
    return total


def _month_end(year: int, month: int) -> dt.date:
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def month_ends_between(start: dt.date, end: dt.date) -> list[dt.date]:
    """Last calendar day of every month from start's month to end's month, inclusive."""
    if start > end:
        return []
    months: list[dt.date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(_month_end(year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def earliest_snapshot_date(db: Session) -> dt.date | None:
    stmt = select(Snapshot.snapshot_date).order_by(Snapshot.snapshot_date.asc()).limit(1)
    return db.scalars(stmt).first()


def latest_snapshot_date(db: Session) -> dt.date | None:
    stmt = select(Snapshot.snapshot_date).order_by(Snapshot.snapshot_date.desc()).limit(1)
    return db.scalars(stmt).first()


def portfolio_trend(
    db: Session,
    fx: ExchangeRateService,
    target_currency: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[TrendPoint]:
    """One point per month-end between start and end (inclusive).

    Gracefully returns an empty list when there isn't enough data yet, rather
    than manufacturing a trend out of a single point.
    """
    if start is None:
        start = earliest_snapshot_date(db)
    if end is None:
        end = latest_snapshot_date(db)
    if start is None or end is None:
        return []

    accounts = list(db.scalars(select(Account)))
    points = []
    for period_end in month_ends_between(start, end):
        value = portfolio_value_as_of(db, fx, target_currency, period_end, accounts=accounts)
        points.append(TrendPoint(date=period_end, value=value))
    return points


def account_trend(
    db: Session,
    fx: ExchangeRateService,
    account: Account,
    target_currency: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[TrendPoint]:
    stmt = select(Snapshot).where(Snapshot.account_id == account.id).order_by(
        Snapshot.snapshot_date
    )
    if start is not None:
        stmt = stmt.where(Snapshot.snapshot_date >= start)
    if end is not None:
        stmt = stmt.where(Snapshot.snapshot_date <= end)
    snapshots = list(db.scalars(stmt))
    return [
        TrendPoint(date=s.snapshot_date, value=convert_snapshot(s, target_currency, fx))
        for s in snapshots
    ]


def accounts_monthly_table(
    db: Session,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
    include_inactive: bool = False,
) -> tuple[list[dt.date], list[AccountMonthlySeries]]:
    """One row per account, one column per month-end — the Excel-style view.

    Values are each account's own native currency (no conversion), matching
    how the source spreadsheet displayed them. A None cell means the account
    didn't exist yet that month, not a zero balance.
    """
    if start is None:
        start = earliest_snapshot_date(db)
    if end is None:
        end = latest_snapshot_date(db)
    if start is None or end is None:
        return [], []

    months = month_ends_between(start, end)

    stmt = select(Account).order_by(Account.name)
    if not include_inactive:
        stmt = stmt.where(Account.is_active.is_(True))
    accounts = list(db.scalars(stmt))

    rows = []
    for account in accounts:
        values: list[Decimal | None] = []
        for month_end in months:
            snapshot = account_balance_as_of(db, account.id, month_end)
            values.append(Decimal(snapshot.value) if snapshot is not None else None)
        rows.append(
            AccountMonthlySeries(
                account_id=account.id,
                account_name=account.name,
                currency=account.currency,
                values=values,
            )
        )
    return months, rows


def account_contributions_by_month(
    db: Session,
    fx: ExchangeRateService,
    target_currency: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
    include_inactive: bool = False,
) -> list[MonthlyContributionRow]:
    """Per-account breakdown of what drove each month's portfolio change.

    Mirrors portfolio_value_as_of's own approach exactly (same
    account_balance_as_of + convert_snapshot calls, converting each snapshot
    at its own recorded date rather than the calendar month-end) so that
    sum(c.delta for c in row.contributions) always equals that month's
    whole-portfolio change from /monthly-changes — an account whose balance
    hasn't changed since last month is not re-priced at a new FX rate just
    because a new month started, same as the whole-portfolio total isn't.
    An account's first-ever snapshot (no prior balance at all) counts as a
    full positive delta, mirroring how a newly-appearing account's balance
    flows straight into the whole-portfolio total the same month. The first
    month in the range has no prior month to diff against, so it's left out
    of the result entirely.
    """
    if start is None:
        start = earliest_snapshot_date(db)
    if end is None:
        end = latest_snapshot_date(db)
    if start is None or end is None:
        return []

    months = month_ends_between(start, end)
    if len(months) < 2:
        return []

    stmt = select(Account).order_by(Account.name)
    if not include_inactive:
        stmt = stmt.where(Account.is_active.is_(True))
    accounts = list(db.scalars(stmt))

    result: list[MonthlyContributionRow] = []
    for month_index in range(1, len(months)):
        month_end = months[month_index]
        previous_month_end = months[month_index - 1]
        contributions: list[AccountContribution] = []
        for account in accounts:
            current_snap = account_balance_as_of(db, account.id, month_end)
            if current_snap is None:
                continue
            current_converted = convert_snapshot(current_snap, target_currency, fx)

            previous_snap = account_balance_as_of(db, account.id, previous_month_end)
            if previous_snap is None:
                delta = current_converted
            else:
                previous_converted = convert_snapshot(previous_snap, target_currency, fx)
                delta = current_converted - previous_converted

            if delta != 0:
                contributions.append(
                    AccountContribution(
                        account_id=account.id, account_name=account.name, delta=delta
                    )
                )
        result.append(MonthlyContributionRow(date=month_end, contributions=contributions))
    return result


def _asset_class_key(account: Account) -> str:
    return account.asset_class.value if hasattr(account.asset_class, "value") else str(
        account.asset_class
    )


def asset_class_trend(
    db: Session,
    fx: ExchangeRateService,
    target_currency: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> tuple[list[dt.date], list[AssetClassSeries]]:
    """portfolio_trend split by asset class: one series per class, one value per month-end.

    Uses exactly the same account set as portfolio_trend (all accounts,
    including inactive — deactivation shouldn't rewrite history) and the same
    account_balance_as_of + convert_snapshot calls as portfolio_value_as_of,
    so for every month the sum across all series equals that month's
    portfolio_trend value. Classes that are zero in every month are left out;
    series are ordered by their latest-month value, largest first.
    """
    if start is None:
        start = earliest_snapshot_date(db)
    if end is None:
        end = latest_snapshot_date(db)
    if start is None or end is None:
        return [], []

    months = month_ends_between(start, end)
    accounts = list(db.scalars(select(Account)))

    per_class: dict[str, list[Decimal]] = {}
    for month_index, period_end in enumerate(months):
        for account in accounts:
            snapshot = account_balance_as_of(db, account.id, period_end)
            if snapshot is None:
                continue
            values = per_class.setdefault(
                _asset_class_key(account), [Decimal(0)] * len(months)
            )
            values[month_index] += convert_snapshot(snapshot, target_currency, fx)

    series = [
        AssetClassSeries(asset_class=key, values=values)
        for key, values in per_class.items()
        if any(v != 0 for v in values)
    ]
    series.sort(key=lambda s: (-s.values[-1], s.asset_class))
    return months, series


def allocation_by_asset_class(
    db: Session, fx: ExchangeRateService, target_currency: str, as_of: dt.date
) -> list[AllocationSlice]:
    accounts = list(db.scalars(select(Account).where(Account.is_active.is_(True))))
    totals: dict[str, Decimal] = {}
    for account in accounts:
        snapshot = account_balance_as_of(db, account.id, as_of)
        if snapshot is None:
            continue
        value = convert_snapshot(snapshot, target_currency, fx)
        key = _asset_class_key(account)
        totals[key] = totals.get(key, Decimal(0)) + value

    grand_total = sum(totals.values(), Decimal(0))
    if grand_total == 0:
        return [AllocationSlice(label=k, value=v, percentage=Decimal(0)) for k, v in totals.items()]
    return [
        AllocationSlice(label=k, value=v, percentage=(v / grand_total) * Decimal(100))
        for k, v in totals.items()
    ]
