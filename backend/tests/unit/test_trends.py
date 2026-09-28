import datetime as dt
from decimal import Decimal

import pytest

from app.services.calculations.trends import (
    average_monthly_change,
    compute_change,
    cumulative_growth,
    historical_high_low,
    period_over_period_changes,
    rolling_average,
)
from app.services.calculations.types import TrendPoint


def pt(day: int, value: str, month: int = 1, year: int = 2024) -> TrendPoint:
    return TrendPoint(date=dt.date(year, month, day), value=Decimal(value))


class TestComputeChange:
    def test_positive_growth(self):
        result = compute_change(Decimal(110), Decimal(100))
        assert result.absolute == Decimal(10)
        assert result.percentage == Decimal(10)

    def test_negative_growth(self):
        result = compute_change(Decimal(90), Decimal(100))
        assert result.absolute == Decimal(-10)
        assert result.percentage == Decimal(-10)

    def test_zero_change(self):
        result = compute_change(Decimal(100), Decimal(100))
        assert result.absolute == Decimal(0)
        assert result.percentage == Decimal(0)

    def test_previous_zero_is_undefined_percentage(self):
        result = compute_change(Decimal(50), Decimal(0))
        assert result.absolute == Decimal(50)
        assert result.percentage is None

    def test_both_zero(self):
        result = compute_change(Decimal(0), Decimal(0))
        assert result.absolute == Decimal(0)
        assert result.percentage is None


class TestCumulativeGrowth:
    def test_growth_over_series(self):
        series = [pt(1, "100"), pt(2, "110", month=2), pt(3, "121", month=3)]
        result = cumulative_growth(series)
        assert result.absolute == Decimal(21)
        assert result.percentage == Decimal(21)

    def test_single_point_returns_none(self):
        assert cumulative_growth([pt(1, "100")]) is None

    def test_empty_series_returns_none(self):
        assert cumulative_growth([]) is None


class TestAverageMonthlyChange:
    def test_average_of_diffs(self):
        series = [pt(1, "100"), pt(2, "110", month=2), pt(3, "126", month=3)]
        # diffs: +10, +16 -> average 13
        assert average_monthly_change(series) == Decimal(13)

    def test_insufficient_data_returns_none(self):
        assert average_monthly_change([pt(1, "100")]) is None
        assert average_monthly_change([]) is None

    def test_negative_average(self):
        series = [pt(1, "100"), pt(2, "80", month=2)]
        assert average_monthly_change(series) == Decimal(-20)


class TestRollingAverage:
    def test_window_of_two(self):
        series = [pt(1, "100"), pt(2, "200", month=2), pt(3, "300", month=3)]
        result = rolling_average(series, window=2)
        assert [p.value for p in result] == [Decimal(150), Decimal(250)]

    def test_window_larger_than_series_returns_empty(self):
        series = [pt(1, "100")]
        assert rolling_average(series, window=3) == []

    def test_invalid_window_raises(self):
        with pytest.raises(ValueError):
            rolling_average([pt(1, "100")], window=0)


class TestHistoricalHighLow:
    def test_high_and_low(self):
        series = [pt(1, "100"), pt(2, "50", month=2), pt(3, "200", month=3)]
        high, low = historical_high_low(series)
        assert high.value == Decimal(200)
        assert low.value == Decimal(50)

    def test_empty_series_returns_none(self):
        assert historical_high_low([]) is None

    def test_single_point_is_both_high_and_low(self):
        high, low = historical_high_low([pt(1, "100")])
        assert high.value == low.value == Decimal(100)


class TestPeriodOverPeriodChanges:
    def test_produces_one_result_per_consecutive_pair(self):
        series = [pt(1, "100"), pt(2, "110", month=2), pt(3, "100", month=3)]
        changes = period_over_period_changes(series)
        assert len(changes) == 2
        assert changes[0].absolute == Decimal(10)
        assert changes[1].absolute == Decimal(-10)

    def test_empty_and_single_point_series(self):
        assert period_over_period_changes([]) == []
        assert period_over_period_changes([pt(1, "100")]) == []
