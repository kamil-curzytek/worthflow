from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, field_validator

from app.database.models import AccountType, AssetClass
from app.domain.currencies.currency import validate_currency


class AccountCreate(BaseModel):
    name: str
    type: AccountType
    asset_class: AssetClass
    currency: str
    institution: str | None = None
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def _valid_currency(cls, v: str) -> str:
        return validate_currency(v)


class AccountUpdate(BaseModel):
    name: str | None = None
    type: AccountType | None = None
    asset_class: AssetClass | None = None
    institution: str | None = None
    is_active: bool | None = None


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: AccountType
    asset_class: AssetClass
    currency: str
    institution: str | None
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime
