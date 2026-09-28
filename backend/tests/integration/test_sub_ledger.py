import datetime as dt
from decimal import Decimal

import pytest

from app.services.sub_ledger import service as calc
from app.services.sub_ledger.metrics import ESPP, TRADING212


def test_set_sub_ledger_value_creates_at_month_end(db):
    entry = calc.set_sub_ledger_value(
        db, category=TRADING212, metric="dividends_monthly", year=2024, month=2, value=Decimal(10)
    )
    assert entry.entry_date == dt.date(2024, 2, 29)  # 2024 is a leap year
    assert entry.value == Decimal(10)


def test_set_sub_ledger_value_corrects_in_place_not_duplicated(db):
    first = calc.set_sub_ledger_value(
        db, category=TRADING212, metric="return", year=2024, month=1, value=Decimal(100)
    )
    second = calc.set_sub_ledger_value(
        db, category=TRADING212, metric="return", year=2024, month=1, value=Decimal(150)
    )
    assert first.id == second.id
    assert second.value == Decimal(150)


def test_set_sub_ledger_value_rejects_unknown_metric(db):
    with pytest.raises(calc.InvalidMetricError):
        calc.set_sub_ledger_value(
            db,
            category=TRADING212,
            metric="not_a_real_metric",
            year=2024,
            month=1,
            value=Decimal(1),
        )


def test_sub_ledger_table_shape(db):
    calc.set_sub_ledger_value(
        db, category=ESPP, metric="stock_qty", year=2024, month=1, value=Decimal("107.75")
    )
    calc.set_sub_ledger_value(
        db, category=ESPP, metric="stock_qty", year=2024, month=2, value=Decimal("107.75")
    )

    months, rows = calc.sub_ledger_table(db, ESPP)
    assert months == [dt.date(2024, 1, 31), dt.date(2024, 2, 29)]
    by_metric = {r.metric: r for r in rows}
    assert by_metric["stock_qty"].values == [Decimal("107.75"), Decimal("107.75")]
    # A metric with no entries yet still appears as a row, all-None.
    assert by_metric["deposit_eur"].values == [None, None]


def test_sub_ledger_table_empty_when_no_data(db):
    months, rows = calc.sub_ledger_table(db, TRADING212)
    assert months == []
    assert rows == []


def test_passive_income_total_uses_real_historical_fx(db, fx):
    from app.services.sub_ledger.metrics import PASSIVE_INCOME

    calc.set_sub_ledger_value(
        db, category=PASSIVE_INCOME, metric="pln_interest", year=2024, month=1, value=Decimal(1000)
    )
    calc.set_sub_ledger_value(
        db, category=PASSIVE_INCOME, metric="n26_interest", year=2024, month=1, value=Decimal(50)
    )
    calc.set_sub_ledger_value(
        db, category=PASSIVE_INCOME, metric="pln_interest", year=2024, month=2, value=Decimal(1200)
    )
    calc.set_sub_ledger_value(
        db, category=PASSIVE_INCOME, metric="n26_interest", year=2024, month=2, value=Decimal(60)
    )

    _, rows = calc.passive_income_table(db, fx, "EUR")
    by_metric = {r.metric: r for r in rows}

    # fake fx fixture: PLN->EUR = 0.23
    assert by_metric["total"].values[0] == Decimal(1000) * Decimal("0.23") + Decimal(50)
    assert by_metric["total"].editable is False
    assert by_metric["gain"].values[0] is None  # first month has no prior month to diff
    total = by_metric["total"].values
    assert by_metric["gain"].values[1] == total[1] - total[0]
    assert by_metric["gain_pct"].editable is False


def test_passive_income_total_none_when_no_sources_reported(db, fx):
    from app.services.sub_ledger.metrics import PASSIVE_INCOME

    calc.set_sub_ledger_value(
        db, category=PASSIVE_INCOME, metric="pln_interest", year=2024, month=1, value=Decimal(100)
    )
    calc.set_sub_ledger_value(
        db, category=PASSIVE_INCOME, metric="pln_interest", year=2024, month=3, value=Decimal(300)
    )

    months, rows = calc.passive_income_table(db, fx, "EUR")
    by_metric = {r.metric: r for r in rows}
    assert months == [dt.date(2024, 1, 31), dt.date(2024, 2, 29), dt.date(2024, 3, 31)]
    assert by_metric["total"].values[1] is None


def _seed_passive_income(db):
    from app.services.sub_ledger.metrics import PASSIVE_INCOME

    for metric, month, value in [
        ("pln_interest", 1, "1000"),
        ("n26_interest", 1, "50"),
        ("t212_interest", 1, "12.34"),
        ("pln_interest", 2, "1200"),
        ("t212_dividends", 2, "7.5"),
        # March deliberately left empty; April has only a EUR source.
        ("n26_interest", 4, "40"),
    ]:
        calc.set_sub_ledger_value(
            db,
            category=PASSIVE_INCOME,
            metric=metric,
            year=2024,
            month=month,
            value=Decimal(value),
        )


def test_passive_income_trend_parts_sum_to_total(db, fx):
    _seed_passive_income(db)

    months, series = calc.passive_income_trend(db, fx, "EUR")
    by_metric = {s.metric: s for s in series}
    assert [s.metric for s in series] == [
        "pln_interest",
        "n26_interest",
        "t212_interest",
        "t212_dividends",
        "total",
    ]
    parts = [s for s in series if s.metric != "total"]

    for i in range(len(months)):
        present = [p.values[i] for p in parts if p.values[i] is not None]
        if present:
            assert sum(present, Decimal(0)) == by_metric["total"].values[i]
        else:
            assert by_metric["total"].values[i] is None

    assert by_metric["total"].values[2] is None  # March: nothing reported
    assert by_metric["pln_interest"].values[3] is None  # None stays None, not 0


def test_passive_income_trend_converts_pln_row(db, fx):
    _seed_passive_income(db)

    _, series = calc.passive_income_trend(db, fx, "EUR")
    by_metric = {s.metric: s for s in series}
    # fake fx fixture: PLN->EUR = 0.23
    assert by_metric["pln_interest"].values[0] == Decimal(1000) * Decimal("0.23")
    assert by_metric["pln_interest"].values[0] != Decimal(1000)
    assert by_metric["pln_interest"].unit == "EUR"
    # EUR rows are unchanged when the target is EUR.
    assert by_metric["n26_interest"].values[0] == Decimal(50)


def test_passive_income_trend_total_matches_table_and_excludes_gain(db, fx):
    _seed_passive_income(db)

    table_months, table_rows = calc.passive_income_table(db, fx, "PLN")
    trend_months, series = calc.passive_income_trend(db, fx, "PLN")
    table_by_metric = {r.metric: r for r in table_rows}
    trend_by_metric = {s.metric: s for s in series}

    assert trend_months == table_months
    assert trend_by_metric["total"].values == table_by_metric["total"].values
    assert "gain" not in trend_by_metric
    assert "gain_pct" not in trend_by_metric


def test_passive_income_trend_empty_when_no_data(db, fx):
    months, series = calc.passive_income_trend(db, fx, "EUR")
    assert months == []
    assert series == []


def test_passive_income_trend_endpoint_shape(db, fx):
    from app.api.routers.sub_ledger import get_passive_income_trend

    _seed_passive_income(db)

    body = get_passive_income_trend(currency="eur", start=None, end=None, db=db, fx=fx)
    assert body["currency"] == "EUR"
    assert body["months"] == ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"]
    assert [s["metric"] for s in body["series"]][-1] == "total"
    total = next(s for s in body["series"] if s["metric"] == "total")
    assert total["label"] == "Total"
    assert total["values"][2] is None
    assert all(v is None or isinstance(v, str) for s in body["series"] for v in s["values"])
    assert Decimal(total["values"][0]) == Decimal(1000) * Decimal("0.23") + Decimal(50) + Decimal(
        "12.34"
    )


def test_passive_income_trend_endpoint_rejects_unknown_currency(db, fx):
    from fastapi import HTTPException

    from app.api.routers.sub_ledger import get_passive_income_trend

    with pytest.raises(HTTPException) as exc_info:
        get_passive_income_trend(currency="XYZ", start=None, end=None, db=db, fx=fx)
    assert exc_info.value.status_code == 400
