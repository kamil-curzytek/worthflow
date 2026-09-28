from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class SubLedgerValueSet(BaseModel):
    metric: str
    year: int
    month: int
    value: Decimal
