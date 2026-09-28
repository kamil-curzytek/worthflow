import datetime as dt
from decimal import Decimal

import pytest

from app.database.models import ExchangeRate
from app.services.exchange_rates.service import ExchangeRateService, ExchangeRateUnavailableError
from tests.conftest import FakeRateProvider


def test_same_currency_is_always_rate_one(db):
    fx = ExchangeRateService(db, FakeRateProvider())
    assert fx.get_rate("EUR", "EUR", dt.date(2024, 1, 1)) == Decimal(1)


def test_fetches_and_caches(db, fake_provider):
    fx = ExchangeRateService(db, fake_provider)
    rate = fx.get_rate("PLN", "EUR", dt.date(2024, 3, 1))
    assert rate == Decimal("0.23")
    assert len(fake_provider.calls) == 1

    # Second call for the same (base, quote, date) must hit the cache, not the provider.
    rate_again = fx.get_rate("PLN", "EUR", dt.date(2024, 3, 1))
    assert rate_again == Decimal("0.23")
    assert len(fake_provider.calls) == 1


def test_different_dates_are_cached_independently(db, fake_provider):
    fx = ExchangeRateService(db, fake_provider)
    fx.get_rate("PLN", "EUR", dt.date(2024, 1, 1))
    fx.get_rate("PLN", "EUR", dt.date(2024, 2, 1))
    assert len(fake_provider.calls) == 2


def test_falls_back_to_most_recent_cached_rate_on_provider_failure(db):
    provider = FakeRateProvider(rates={("PLN", "EUR"): Decimal("0.23")})
    fx = ExchangeRateService(db, provider)
    fx.get_rate("PLN", "EUR", dt.date(2024, 1, 1))  # caches Jan rate

    provider.fail = True
    lookup = fx.get_rate_with_metadata("PLN", "EUR", dt.date(2024, 2, 1))
    assert lookup.rate == Decimal("0.23")
    assert lookup.is_stale_fallback is True
    assert lookup.rate_date == dt.date(2024, 1, 1)


def test_raises_when_no_cache_and_provider_unreachable(db):
    provider = FakeRateProvider(fail=True)
    fx = ExchangeRateService(db, provider)
    with pytest.raises(ExchangeRateUnavailableError):
        fx.get_rate("PLN", "EUR", dt.date(2024, 1, 1))


def test_convert_applies_rate(db, fake_provider):
    fx = ExchangeRateService(db, fake_provider)
    converted = fx.convert(Decimal(100), "PLN", "EUR", dt.date(2024, 1, 1))
    assert converted == Decimal("23.00")


def test_concurrent_cache_write_does_not_crash(db):
    """Simulates two concurrent requests both missing the cache and racing to
    insert the same (base, quote, date, source) row — the scenario that broke
    the live dashboard when it fired several portfolio requests in parallel
    on a currency switch. The loser of the race must fall back to the
    winner's row instead of raising IntegrityError.
    """

    class RaceyProvider(FakeRateProvider):
        def fetch_rate(self, base, quote, on_date):
            rate = super().fetch_rate(base, quote, on_date)
            # Simulate another request's session committing the same row
            # between our cache-miss check and our own insert.
            db.add(
                ExchangeRate(
                    base_currency=base,
                    quote_currency=quote,
                    rate=rate,
                    rate_date=on_date,
                    source=self.name,
                )
            )
            db.commit()
            return rate

    provider = RaceyProvider(rates={("PLN", "EUR"): Decimal("0.23")})
    fx = ExchangeRateService(db, provider)

    lookup = fx.get_rate_with_metadata("PLN", "EUR", dt.date(2024, 1, 1))
    assert lookup.rate == Decimal("0.23")
    assert lookup.is_stale_fallback is False

    # Exactly one row exists — no duplicate, no crash.
    rows = db.query(ExchangeRate).filter_by(base_currency="PLN", quote_currency="EUR").all()
    assert len(rows) == 1
