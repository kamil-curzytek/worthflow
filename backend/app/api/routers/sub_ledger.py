import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_fx_service
from app.domain.currencies.currency import UnsupportedCurrencyError, validate_currency
from app.domain.sub_ledger.schemas import SubLedgerValueSet
from app.services.exchange_rates.service import ExchangeRateService
from app.services.sub_ledger import service as calc
from app.services.sub_ledger.metrics import ESPP, PASSIVE_INCOME, TRADING212

router = APIRouter(prefix="/api/sub-ledger", tags=["sub-ledger"])

_DIRECT_CATEGORIES = {TRADING212, ESPP}


def _row_dict(row: calc.SubLedgerRow) -> dict:
    return {
        "metric": row.metric,
        "label": row.label,
        "unit": row.unit,
        "editable": row.editable,
        "values": [str(v) if v is not None else None for v in row.values],
    }


@router.get("/passive-income")
def get_passive_income_table(
    currency: str = "EUR",
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    try:
        currency = validate_currency(currency)
    except UnsupportedCurrencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    months, rows = calc.passive_income_table(db, fx, currency, start=start, end=end)
    return {
        "category": PASSIVE_INCOME,
        "currency": currency,
        "months": [m.isoformat() for m in months],
        "rows": [_row_dict(r) for r in rows],
    }


@router.get("/passive-income/trend")
def get_passive_income_trend(
    currency: str = "EUR",
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
    fx: ExchangeRateService = Depends(get_fx_service),
):
    try:
        currency = validate_currency(currency)
    except UnsupportedCurrencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    months, series = calc.passive_income_trend(db, fx, currency, start=start, end=end)
    return {
        "currency": currency,
        "months": [m.isoformat() for m in months],
        "series": [
            {
                "metric": s.metric,
                "label": s.label,
                "values": [str(v) if v is not None else None for v in s.values],
            }
            for s in series
        ],
    }


@router.get("/{category}")
def get_sub_ledger_table(
    category: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
    db: Session = Depends(get_db),
):
    if category not in _DIRECT_CATEGORIES:
        raise HTTPException(
            status_code=404, detail=f"Unknown sub-ledger category {category!r}"
        )
    months, rows = calc.sub_ledger_table(db, category, start=start, end=end)
    return {
        "category": category,
        "months": [m.isoformat() for m in months],
        "rows": [_row_dict(r) for r in rows],
    }


@router.put("/{category}/monthly")
def set_sub_ledger_value(category: str, payload: SubLedgerValueSet, db: Session = Depends(get_db)):
    if category not in {TRADING212, ESPP, PASSIVE_INCOME}:
        raise HTTPException(
            status_code=404, detail=f"Unknown sub-ledger category {category!r}"
        )
    if not 1 <= payload.month <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    try:
        entry = calc.set_sub_ledger_value(
            db,
            category=category,
            metric=payload.metric,
            year=payload.year,
            month=payload.month,
            value=payload.value,
        )
    except calc.InvalidMetricError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "category": entry.category,
        "metric": entry.metric,
        "date": entry.entry_date.isoformat(),
        "value": str(entry.value),
    }
