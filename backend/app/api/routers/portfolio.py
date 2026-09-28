import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_fx_service
from app.database.models import Account
from app.domain.currencies.currency import UnsupportedCurrencyError, validate_currency
from app.services import accounts_service
from app.services.calculations import portfolio as calc
from app.services.calculations.trends import (
    average_monthly_change,
    compute_change,
    cumulative_growth,
    historical_high_low,
)
from app.services.exchange_rates.service import ExchangeRateService

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _currency(currency: str) -> str:
    try:
        return validate_currency(currency)
    except UnsupportedCurrencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _point_dict(p):
    return {"date": p.date.isoformat(), "value": str(p.value)}


@router.get("/value")
def portfolio_value(
    currency: str = Query("EUR"),
    as_of: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    currency = _currency(currency)
    as_of = as_of or dt.date.today()
    value = calc.portfolio_value_as_of(db, fx, currency, as_of)
    return {"currency": currency, "as_of": as_of.isoformat(), "value": str(value)}


@router.get("/trend")
def portfolio_trend(
    currency: str = Query("EUR"),
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    currency = _currency(currency)
    series = calc.portfolio_trend(db, fx, currency, start=start, end=end)

    growth = cumulative_growth(series)
    avg_change = average_monthly_change(series)
    high_low = historical_high_low(series)

    return {
        "currency": currency,
        "points": [_point_dict(p) for p in series],
        "cumulative_growth": (
            {
                "absolute": str(growth.absolute),
                "percentage": str(growth.percentage) if growth.percentage is not None else None,
            }
            if growth
            else None
        ),
        "average_monthly_change": str(avg_change) if avg_change is not None else None,
        "high": _point_dict(high_low[0]) if high_low else None,
        "low": _point_dict(high_low[1]) if high_low else None,
    }


@router.get("/monthly-changes")
def monthly_changes(
    currency: str = Query("EUR"),
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    currency = _currency(currency)
    series = calc.portfolio_trend(db, fx, currency, start=start, end=end)
    rows = []
    previous: Decimal | None = None
    for point in series:
        change = compute_change(point.value, previous) if previous is not None else None
        rows.append(
            {
                "date": point.date.isoformat(),
                "total": str(point.value),
                "change_absolute": str(change.absolute) if change else None,
                "change_percentage": (
                    str(change.percentage) if change and change.percentage is not None else None
                ),
            }
        )
        previous = point.value
    return {"currency": currency, "rows": rows}


@router.get("/accounts-monthly")
def accounts_monthly(
    start: dt.date | None = None,
    end: dt.date | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """Excel-style matrix: one row per account, one column per month, values
    in each account's own native currency (no conversion)."""
    months, rows = calc.accounts_monthly_table(
        db, start=start, end=end, include_inactive=include_inactive
    )
    return {
        "months": [m.isoformat() for m in months],
        "accounts": [
            {
                "account_id": r.account_id,
                "account_name": r.account_name,
                "currency": r.currency,
                "values": [str(v) if v is not None else None for v in r.values],
            }
            for r in rows
        ],
    }


@router.get("/allocation")
def allocation(
    currency: str = Query("EUR"),
    as_of: dt.date | None = None,
    by: str = Query("asset_class", pattern="^(asset_class|currency|account)$"),
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    currency = _currency(currency)
    as_of = as_of or dt.date.today()

    if by == "asset_class":
        slices = calc.allocation_by_asset_class(db, fx, currency, as_of)
    else:
        slices = _allocation_by(db, fx, currency, as_of, by)

    return {
        "currency": currency,
        "as_of": as_of.isoformat(),
        "slices": [
            {"label": s.label, "value": str(s.value), "percentage": str(s.percentage)}
            for s in slices
        ],
    }


@router.get("/asset-class-trend")
def asset_class_trend(
    currency: str = Query("EUR"),
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    """Portfolio trend split by asset class; per-month values sum to /trend's."""
    currency = _currency(currency)
    months, series = calc.asset_class_trend(db, fx, currency, start=start, end=end)
    return {
        "currency": currency,
        "months": [m.isoformat() for m in months],
        "series": [
            {"asset_class": s.asset_class, "values": [str(v) for v in s.values]}
            for s in series
        ],
    }


def _allocation_by(db, fx, currency, as_of, by: str):
    from decimal import Decimal as D

    from app.services.calculations.types import AllocationSlice

    accounts: list[Account] = accounts_service.list_accounts(db, include_inactive=False)
    totals: dict[str, D] = {}
    for account in accounts:
        snapshot = calc.account_balance_as_of(db, account.id, as_of)
        if snapshot is None:
            continue
        value = calc.convert_snapshot(snapshot, currency, fx)
        key = account.currency if by == "currency" else account.name
        totals[key] = totals.get(key, D(0)) + value

    grand_total = sum(totals.values(), D(0))
    if grand_total == 0:
        return [AllocationSlice(label=k, value=v, percentage=D(0)) for k, v in totals.items()]
    return [
        AllocationSlice(label=k, value=v, percentage=(v / grand_total) * D(100))
        for k, v in totals.items()
    ]


@router.get("/monthly-contributions")
def monthly_contributions(
    currency: str = Query("EUR"),
    start: dt.date | None = None,
    end: dt.date | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    """Per-account breakdown of what drove each month's portfolio change."""
    currency = _currency(currency)
    rows = calc.account_contributions_by_month(
        db, fx, currency, start=start, end=end, include_inactive=include_inactive
    )
    return {
        "currency": currency,
        "rows": [
            {
                "date": row.date.isoformat(),
                "contributions": [
                    {
                        "account_id": c.account_id,
                        "account_name": c.account_name,
                        "delta": str(c.delta),
                    }
                    for c in row.contributions
                ],
            }
            for row in rows
        ],
    }


@router.get("/accounts/{account_id}/trend")
def account_trend(
    account_id: str,
    currency: str = Query("EUR"),
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    currency = _currency(currency)
    try:
        account = accounts_service.get_account(db, account_id)
    except accounts_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    series = calc.account_trend(db, fx, account, currency, start=start, end=end)
    return {
        "account_id": account_id,
        "currency": currency,
        "points": [_point_dict(p) for p in series],
    }
