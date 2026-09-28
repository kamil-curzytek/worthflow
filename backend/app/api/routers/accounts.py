from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.database.models import User
from app.domain.accounts.schemas import AccountCreate, AccountRead, AccountUpdate
from app.services import accounts_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountRead])
def list_accounts(include_inactive: bool = False, db: Session = Depends(get_db)):
    return accounts_service.list_accounts(db, include_inactive=include_inactive)


@router.post("", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return accounts_service.create_account(db, user.id, payload)
    except accounts_service.DuplicateAccountError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db)):
    try:
        return accounts_service.update_account(db, account_id, payload)
    except accounts_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{account_id}/deactivate", response_model=AccountRead)
def deactivate_account(account_id: str, db: Session = Depends(get_db)):
    try:
        return accounts_service.deactivate_account(db, account_id)
    except accounts_service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
