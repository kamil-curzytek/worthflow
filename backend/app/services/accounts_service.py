"""Account CRUD. Shared by the API and the CLI — no business logic lives in either."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Account, AccountType, AssetClass
from app.domain.accounts.schemas import AccountCreate, AccountUpdate
from app.domain.currencies.currency import validate_currency


class DuplicateAccountError(ValueError):
    pass


class AccountNotFoundError(ValueError):
    pass


def list_accounts(db: Session, *, include_inactive: bool = False) -> list[Account]:
    stmt = select(Account).order_by(Account.name)
    if not include_inactive:
        stmt = stmt.where(Account.is_active.is_(True))
    return list(db.scalars(stmt))


def get_account(db: Session, account_id: str) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise AccountNotFoundError(f"No account with id {account_id!r}")
    return account


def get_account_by_name(db: Session, user_id: str, name: str) -> Account | None:
    stmt = select(Account).where(Account.user_id == user_id, Account.name == name)
    return db.scalars(stmt).first()


def create_account(db: Session, user_id: str, payload: AccountCreate) -> Account:
    if get_account_by_name(db, user_id, payload.name) is not None:
        raise DuplicateAccountError(f"Account {payload.name!r} already exists")
    account = Account(
        user_id=user_id,
        name=payload.name,
        type=payload.type,
        asset_class=payload.asset_class,
        currency=validate_currency(payload.currency),
        institution=payload.institution,
        is_active=payload.is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(db: Session, account_id: str, payload: AccountUpdate) -> Account:
    account = get_account(db, account_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


def deactivate_account(db: Session, account_id: str) -> Account:
    return update_account(db, account_id, AccountUpdate(is_active=False))


def get_or_create_account(
    db: Session,
    user_id: str,
    *,
    name: str,
    type: AccountType,
    asset_class: AssetClass,
    currency: str,
) -> Account:
    existing = get_account_by_name(db, user_id, name)
    if existing is not None:
        return existing
    return create_account(
        db,
        user_id,
        AccountCreate(name=name, type=type, asset_class=asset_class, currency=currency),
    )
