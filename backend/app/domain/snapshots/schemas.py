from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.database.models import SnapshotSource


class SnapshotCreate(BaseModel):
    account_id: str
    snapshot_date: dt.date
    value: Decimal
    note: str | None = None
    source: SnapshotSource = SnapshotSource.MANUAL


class SnapshotUpdate(BaseModel):
    value: Decimal | None = None
    note: str | None = None


class MonthlyValueSet(BaseModel):
    account_id: str
    year: int
    month: int
    value: Decimal
    note: str | None = None


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    snapshot_date: dt.date
    value: Decimal
    currency: str
    source: SnapshotSource
    note: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
