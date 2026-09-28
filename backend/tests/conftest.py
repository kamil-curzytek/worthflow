"""Test fixtures. Always use an isolated in-memory database — never the real
data/private/finance.db. Services take a Session explicitly, so tests never
need to touch app.database.session's global engine.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import models  # noqa: F401  (registers tables on Base.metadata)
from app.database.base import Base
from app.services.exchange_rates.provider import ExchangeRateProvider, ExchangeRateProviderError
from app.services.exchange_rates.service import ExchangeRateService
from app.services.users_service import get_or_create_local_user


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db):
    return get_or_create_local_user(db)


class FakeRateProvider(ExchangeRateProvider):
    """Deterministic in-memory FX provider for tests — no network calls."""

    name = "fake"

    def __init__(self, rates: dict[tuple[str, str], Decimal] | None = None, fail: bool = False):
        self.rates = rates or {}
        self.fail = fail
        self.calls: list[tuple[str, str, dt.date]] = []

    def fetch_rate(self, base: str, quote: str, on_date: dt.date) -> Decimal:
        self.calls.append((base, quote, on_date))
        if self.fail:
            raise ExchangeRateProviderError("simulated failure")
        if (base, quote) not in self.rates:
            raise ExchangeRateProviderError(f"no fake rate configured for {base}->{quote}")
        return self.rates[(base, quote)]


@pytest.fixture()
def fake_provider():
    return FakeRateProvider(
        rates={
            ("PLN", "EUR"): Decimal("0.23"),
            ("EUR", "PLN"): Decimal("4.35"),
            ("USD", "EUR"): Decimal("0.87"),
            ("EUR", "USD"): Decimal("1.15"),
            ("USD", "PLN"): Decimal("3.78"),
            ("PLN", "USD"): Decimal("0.26"),
        }
    )


@pytest.fixture()
def fx(db, fake_provider):
    return ExchangeRateService(db, fake_provider)
