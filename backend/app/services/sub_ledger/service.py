"""Read/write access to sub-ledger tabs (Trading212, ESPP, Passive income).

set_sub_ledger_value mirrors snapshots_service.set_monthly_value exactly —
same find-in-month-or-correct-in-place, create-at-month-end-if-absent
behavior — because it's the same UX (an editable Excel-style grid) applied to
a different kind of row.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import SubLedgerEntry
from app.services.calculations.portfolio import month_ends_between
from app.services.calculations.trends import compute_change
from app.services.calculations.types import ChangeResult
from app.services.exchange_rates.service import ExchangeRateService
from app.services.sub_ledger.metrics import PASSIVE_INCOME, metric_defs


class InvalidMetricError(ValueError):
    pass


@dataclass(frozen=True)
class SubLedgerRow:
    metric: str
    label: str
    unit: str
    editable: bool
    values: list[Decimal | None]


def _earliest_entry_date(db: Session, category: str) -> dt.date | None:
    stmt = select(func.min(SubLedgerEntry.entry_date)).where(
        SubLedgerEntry.category == category
    )
    return db.scalar(stmt)


def _latest_entry_date(db: Session, category: str) -> dt.date | None:
    stmt = select(func.max(SubLedgerEntry.entry_date)).where(
        SubLedgerEntry.category == category
    )
    return db.scalar(stmt)


def set_sub_ledger_value(
    db: Session, *, category: str, metric: str, year: int, month: int, value: Decimal
) -> SubLedgerEntry:
    matching = next((m for m in metric_defs(category) if m.key == metric), None)
    if matching is None:
        raise InvalidMetricError(f"{metric!r} is not a known metric for category {category!r}")
    if not matching.editable:
        raise InvalidMetricError(
            f"{metric!r} is computed from other rows and can't be edited directly."
        )

    month_start = dt.date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    month_end = dt.date(year, month, days_in_month)

    stmt = select(SubLedgerEntry).where(
        SubLedgerEntry.category == category,
        SubLedgerEntry.metric == metric,
        SubLedgerEntry.entry_date >= month_start,
        SubLedgerEntry.entry_date <= month_end,
    )
    existing = db.scalars(stmt).first()
    if existing is not None:
        existing.value = value
        db.commit()
        db.refresh(existing)
        return existing

    entry = SubLedgerEntry(category=category, metric=metric, entry_date=month_end, value=value)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def sub_ledger_table(
    db: Session,
    category: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> tuple[list[dt.date], list[SubLedgerRow]]:
    """One row per configured metric, one column per month-end.

    Same shape as calculations.portfolio.accounts_monthly_table: a None cell
    means no entry recorded for that metric that month, not a zero.
    """
    if start is None:
        start = _earliest_entry_date(db, category)
    if end is None:
        end = _latest_entry_date(db, category)
    if start is None or end is None:
        return [], []

    months = month_ends_between(start, end)

    stmt = select(SubLedgerEntry).where(
        SubLedgerEntry.category == category,
        SubLedgerEntry.entry_date >= months[0],
        SubLedgerEntry.entry_date <= months[-1],
    )
    entries = list(db.scalars(stmt))
    by_metric_date: dict[tuple[str, dt.date], Decimal] = {
        (e.metric, e.entry_date): Decimal(e.value) for e in entries
    }

    rows = []
    for metric_def in metric_defs(category):
        values = [by_metric_date.get((metric_def.key, month)) for month in months]
        rows.append(
            SubLedgerRow(
                metric=metric_def.key,
                label=metric_def.label,
                unit=metric_def.unit,
                editable=metric_def.editable,
                values=values,
            )
        )
    return months, rows


def _convert_rows(
    fx: ExchangeRateService,
    target_currency: str,
    months: list[dt.date],
    rows: list[SubLedgerRow],
) -> list[SubLedgerRow]:
    """Each raw row converted from its own unit into target_currency, using
    the real historical rate at each month-end. None stays None."""
    converted = []
    for row in rows:
        values = [
            fx.convert(value, row.unit, target_currency, month) if value is not None else None
            for value, month in zip(row.values, months, strict=True)
        ]
        converted.append(SubLedgerRow(row.metric, row.label, target_currency, False, values))
    return converted


def _sum_parts(converted: list[SubLedgerRow], month_count: int) -> list[Decimal | None]:
    """Per-month sum of already-converted parts; None when no part reported."""
    totals: list[Decimal | None] = []
    for i in range(month_count):
        parts = [v for row in converted if (v := row.values[i]) is not None]
        totals.append(sum(parts, Decimal(0)) if parts else None)
    return totals


def passive_income_table(
    db: Session,
    fx: ExchangeRateService,
    target_currency: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> tuple[list[dt.date], list[SubLedgerRow]]:
    """The four raw Passive income metrics, plus computed total/gain/gain%.

    Total/gain are computed here rather than imported, using real historical
    FX rates for the PLN row — the same principle every other total in this
    app already follows (see docs/architecture.md's note on the source
    sheet's one-static-rate shortcut).
    """
    months, rows = sub_ledger_table(db, PASSIVE_INCOME, start=start, end=end)
    if not months:
        return months, rows

    totals = _sum_parts(_convert_rows(fx, target_currency, months, rows), len(months))

    gains: list[Decimal | None] = [None]
    gain_pcts: list[Decimal | None] = [None]
    for previous, current in pairwise(totals):
        if previous is None or current is None:
            gains.append(None)
            gain_pcts.append(None)
            continue
        change: ChangeResult = compute_change(current, previous)
        gains.append(change.absolute)
        gain_pcts.append(change.percentage)

    rows.append(SubLedgerRow("total", "Total", target_currency, False, totals))
    rows.append(SubLedgerRow("gain", "Gain", target_currency, False, gains))
    rows.append(SubLedgerRow("gain_pct", "Gain %", "percent", False, gain_pcts))
    return months, rows


def passive_income_trend(
    db: Session,
    fx: ExchangeRateService,
    target_currency: str,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> tuple[list[dt.date], list[SubLedgerRow]]:
    """Chart series for the Passive income tab: each raw source converted into
    target_currency at its month-end rate, plus the total.

    Uses the same conversion helpers as passive_income_table, so each month's
    converted parts sum exactly to that month's total. No gain/gain% — those
    are table-only.
    """
    months, rows = sub_ledger_table(db, PASSIVE_INCOME, start=start, end=end)
    if not months:
        return months, []

    converted = _convert_rows(fx, target_currency, months, rows)
    totals = _sum_parts(converted, len(months))
    converted.append(SubLedgerRow("total", "Total", target_currency, False, totals))
    return months, converted
