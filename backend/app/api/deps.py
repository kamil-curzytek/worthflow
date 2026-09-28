from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.models import User
from app.database.session import get_db as _get_db
from app.services.exchange_rates.factory import build_exchange_rate_service
from app.services.exchange_rates.service import ExchangeRateService
from app.services.users_service import get_or_create_local_user


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


def get_current_user(db: Session = Depends(get_db)) -> User:
    return get_or_create_local_user(db)


def get_fx_service(db: Session = Depends(get_db)) -> ExchangeRateService:
    return build_exchange_rate_service(db)
