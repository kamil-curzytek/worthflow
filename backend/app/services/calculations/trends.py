"""Pure, deterministic financial math — no DB, no I/O.

Everything here must be exactly reproducible given the same inputs. AI never
does this arithmetic; it only interprets the output of these functions.
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from itertools import pairwise

from app.services.calculations.types import ChangeResult, TrendPoint

getcontext().prec = 28


def compute_change(current: Decimal, previous: Decimal) -> ChangeResult:
    """Absolute and percentage change from previous -> current.

    Percentage is None (undefined) when previous is 0 — you cannot express
    "growth from nothing" as a percentage, and pretending it's some huge
    number would be misleading.
    """
    absolute = current - previous
    if previous == 0:
        return ChangeResult(absolute=absolute, percentage=None)
    percentage = (absolute / previous) * Decimal(100)
    return ChangeResult(absolute=absolute, percentage=percentage)


def cumulative_growth(series: list[TrendPoint]) -> ChangeResult | None:
    """Change from the first point in the series to the last. None if <2 points."""
    if len(series) < 2:
        return None
    return compute_change(series[-1].value, series[0].value)


def average_monthly_change(series: list[TrendPoint]) -> Decimal | None:
    """Mean of month-over-month absolute changes. None if <2 points."""
    if len(series) < 2:
        return None
    diffs = [b.value - a.value for a, b in pairwise(series)]
    return sum(diffs, Decimal(0)) / Decimal(len(diffs))


def rolling_average(series: list[TrendPoint], window: int) -> list[TrendPoint]:
    """Trailing rolling average with the given window size.

    The first (window - 1) points have no full window and are omitted, rather
    than computed over a partial (and misleading) window.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if len(series) < window:
        return []
    result: list[TrendPoint] = []
    for i in range(window - 1, len(series)):
        chunk = series[i - window + 1 : i + 1]
        avg = sum((p.value for p in chunk), Decimal(0)) / Decimal(window)
        result.append(TrendPoint(date=series[i].date, value=avg))
    return result


def historical_high_low(series: list[TrendPoint]) -> tuple[TrendPoint, TrendPoint] | None:
    """(high, low) points in the series. None if the series is empty."""
    if not series:
        return None
    high = max(series, key=lambda p: p.value)
    low = min(series, key=lambda p: p.value)
    return high, low


def period_over_period_changes(series: list[TrendPoint]) -> list[ChangeResult]:
    """One ChangeResult per consecutive pair in the series."""
    return [compute_change(b.value, a.value) for a, b in pairwise(series)]
