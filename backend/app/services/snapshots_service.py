"""Snapshot CRUD — the historical balance ledger.

Adding a snapshot for a (account, date) pair that already exists is rejected
by default: history is additive, not overwritten. Correcting a mistaken value
is a separate, explicit operation (update_snapshot).
"""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Account, Snapshot, SnapshotSource
from app.services.accounts_service import get_account


class DuplicateSnapshotError(ValueError):
    pass


class SnapshotNotFoundError(ValueError):
    pass


def list_snapshots(
    db: Session,
    *,
    account_id: str | None = None,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> list[Snapshot]:
    stmt = select(Snapshot).order_by(Snapshot.snapshot_date)
    if account_id is not None:
        stmt = stmt.where(Snapshot.account_id == account_id)
    if start_date is not None:
        stmt = stmt.where(Snapshot.snapshot_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Snapshot.snapshot_date <= end_date)
    return list(db.scalars(stmt))


def get_snapshot(db: Session, snapshot_id: str) -> Snapshot:
    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise SnapshotNotFoundError(f"No snapshot with id {snapshot_id!r}")
    return snapshot


def find_snapshot(db: Session, account_id: str, snapshot_date: dt.date) -> Snapshot | None:
    stmt = select(Snapshot).where(
        Snapshot.account_id == account_id, Snapshot.snapshot_date == snapshot_date
    )
    return db.scalars(stmt).first()


def create_snapshot(
    db: Session,
    *,
    account: Account,
    snapshot_date: dt.date,
    value: Decimal,
    source: SnapshotSource = SnapshotSource.MANUAL,
    note: str | None = None,
    import_batch_id: str | None = None,
    allow_overwrite: bool = False,
) -> Snapshot:
    existing = find_snapshot(db, account.id, snapshot_date)
    if existing is not None:
        if not allow_overwrite:
            raise DuplicateSnapshotError(
                f"{account.name} already has a snapshot for {snapshot_date}. "
                "Use update_snapshot to correct it."
            )
        existing.value = value
        existing.note = note
        db.commit()
        db.refresh(existing)
        return existing

    snapshot = Snapshot(
        account_id=account.id,
        snapshot_date=snapshot_date,
        value=value,
        currency=account.currency,
        source=source,
        note=note,
        import_batch_id=import_batch_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def update_snapshot(
    db: Session, snapshot_id: str, *, value: Decimal | None = None, note: str | None = None
) -> Snapshot:
    snapshot = get_snapshot(db, snapshot_id)
    if value is not None:
        snapshot.value = value
    if note is not None:
        snapshot.note = note
    db.commit()
    db.refresh(snapshot)
    return snapshot


def delete_snapshot(db: Session, snapshot_id: str) -> None:
    snapshot = get_snapshot(db, snapshot_id)
    db.delete(snapshot)
    db.commit()


def latest_snapshot_per_account(db: Session, account_id: str) -> Snapshot | None:
    stmt = (
        select(Snapshot)
        .where(Snapshot.account_id == account_id)
        .order_by(Snapshot.snapshot_date.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def set_monthly_value(
    db: Session,
    *,
    account: Account,
    year: int,
    month: int,
    value: Decimal,
    source: SnapshotSource = SnapshotSource.MANUAL,
    note: str | None = None,
) -> Snapshot:
    """Add or correct this account's value for a calendar month — the inline
    edit behind the Monthly Values grid ("click a cell to add or adjust it").

    Unlike create_snapshot (keyed on an exact date), this is keyed on
    (account, year, month): if any snapshot already exists in that month
    (whatever day it's actually dated — e.g. an Excel import landed on the
    1st), that one is corrected in place rather than adding a second,
    redundant snapshot for the same month. Only when the month has no
    snapshot yet is a new one created, dated on the month's last day.
    """
    month_start = dt.date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    month_end = dt.date(year, month, days_in_month)

    stmt = select(Snapshot).where(
        Snapshot.account_id == account.id,
        Snapshot.snapshot_date >= month_start,
        Snapshot.snapshot_date <= month_end,
    )
    existing = db.scalars(stmt).first()
    if existing is not None:
        existing.value = value
        if note is not None:
            existing.note = note
        db.commit()
        db.refresh(existing)
        return existing

    return create_snapshot(
        db, account=account, snapshot_date=month_end, value=value, source=source, note=note
    )


def add_or_update_monthly_snapshot(
    db: Session,
    *,
    account: Account,
    snapshot_date: dt.date,
    value: Decimal,
    source: SnapshotSource = SnapshotSource.MANUAL,
    note: str | None = None,
) -> Snapshot:
    """Convenience used by the dashboard's 'quick monthly update' flow.

    Unlike create_snapshot, this allows overwriting an existing value for the
    same date on purpose (the user correcting this month's number), while
    still never touching any *other* date's history.
    """
    return create_snapshot(
        db,
        account=account,
        snapshot_date=snapshot_date,
        value=value,
        source=source,
        note=note,
        allow_overwrite=True,
    )


__all__ = [
    "DuplicateSnapshotError",
    "SnapshotNotFoundError",
    "add_or_update_monthly_snapshot",
    "create_snapshot",
    "delete_snapshot",
    "find_snapshot",
    "get_account",
    "get_snapshot",
    "latest_snapshot_per_account",
    "list_snapshots",
    "set_monthly_value",
    "update_snapshot",
]
