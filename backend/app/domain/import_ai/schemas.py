from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.database.models import AccountType, AssetClass


class ProposedEntryDto(BaseModel):
    date: str
    value: str


class ProposedAccountDto(BaseModel):
    source_label: str
    suggested_name: str
    suggested_currency: str
    suggested_type: str
    suggested_asset_class: str
    entries: list[ProposedEntryDto]


class ImportInterpretationDto(BaseModel):
    summary: str
    accounts: list[ProposedAccountDto]
    warnings: list[str]
    source_path: str


class AiEntrySelectionDto(BaseModel):
    date: dt.date
    value: Decimal
    include: bool = True


class AiAccountSelectionDto(BaseModel):
    name: str
    currency: str
    type: AccountType
    asset_class: AssetClass
    include: bool = True
    entries: list[AiEntrySelectionDto]


class AiImportCommitRequest(BaseModel):
    accounts: list[AiAccountSelectionDto]
