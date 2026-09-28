import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.snapshots.schemas import (
    MonthlyValueSet,
    SnapshotCreate,
    SnapshotRead,
    SnapshotUpdate,
)
from app.services import accounts_service, snapshots_service

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotRead])
def list_snapshots(
    account_id: str | None = None,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    db: Session = Depends(get_db),
):
    return snapshots_service.list_snapshots(
        db, account_id=account_id, start_date=start_date, end_date=end_date
    )


@router.post("", response_model=SnapshotRead, status_code=201)
def create_snapshot(payload: SnapshotCreate, db: Session = Depends(get_db)):
    try:
        account = accounts_service.get_account(db, payload.account_id)
        return snapshots_service.create_snapshot(
            db,
            account=account,
            snapshot_date=payload.snapshot_date,
            value=payload.value,
            source=payload.source,
            note=payload.note,
        )
    except accounts_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except snapshots_service.DuplicateSnapshotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/monthly", response_model=SnapshotRead)
def set_monthly_value(payload: MonthlyValueSet, db: Session = Depends(get_db)):
    """Add or correct a value for a whole calendar month — the endpoint
    behind clicking a cell in the Monthly Values grid."""
    if not 1 <= payload.month <= 12:
        raise HTTPException(status_code=400, detail="month must be between 1 and 12")
    try:
        account = accounts_service.get_account(db, payload.account_id)
    except accounts_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return snapshots_service.set_monthly_value(
        db,
        account=account,
        year=payload.year,
        month=payload.month,
        value=payload.value,
        note=payload.note,
    )


@router.patch("/{snapshot_id}", response_model=SnapshotRead)
def update_snapshot(snapshot_id: str, payload: SnapshotUpdate, db: Session = Depends(get_db)):
    try:
        return snapshots_service.update_snapshot(
            db, snapshot_id, value=payload.value, note=payload.note
        )
    except snapshots_service.SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: str, db: Session = Depends(get_db)):
    try:
        snapshots_service.delete_snapshot(db, snapshot_id)
    except snapshots_service.SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
