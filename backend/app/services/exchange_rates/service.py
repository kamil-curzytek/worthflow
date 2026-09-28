"""Exchange-rate service: DB-cached, historically reproducible, degrades gracefully.

Every rate ever used is persisted with its date and source, so re-computing a
past month's totals always uses the rate that was actually used then — not
whatever the live rate happens to be today.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import ExchangeRate
from app.services.exchange_rates.provider import ExchangeRateProvider, ExchangeRateProviderError


class ExchangeRateUnavailableError(Exception):
    """No cached rate and the provider could not be reached."""


@dataclass(frozen=True)
class RateLookup:
    rate: Decimal
    rate_date: dt.date  # the date the rate actually applies to
    is_stale_fallback: bool  # True if the live provider failed and this is an older cached rate


class ExchangeRateService:
    def __init__(self, db: Session, provider: ExchangeRateProvider):
        self._db = db
        self._provider = provider

    def _cached(self, base: str, quote: str, on_date: dt.date) -> ExchangeRate | None:
        stmt = select(ExchangeRate).where(
            ExchangeRate.base_currency == base,
            ExchangeRate.quote_currency == quote,
            ExchangeRate.rate_date == on_date,
            ExchangeRate.source == self._provider.name,
        )
        return self._db.scalars(stmt).first()

    def _most_recent_cached_on_or_before(
        self, base: str, quote: str, on_date: dt.date
    ) -> ExchangeRate | None:
        stmt = (
            select(ExchangeRate)
            .where(
                ExchangeRate.base_currency == base,
                ExchangeRate.quote_currency == quote,
                ExchangeRate.rate_date <= on_date,
            )
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )
        return self._db.scalars(stmt).first()

    def get_rate_with_metadata(self, base: str, quote: str, on_date: dt.date) -> RateLookup:
        """Get the base->quote rate for on_date, fetching+caching if needed.

        Falls back to the most recent cached rate on or before on_date if the
        live provider is unreachable (no internet, rate limited, API down),
        so the app keeps working offline using the last known-good rates. The
        returned RateLookup says explicitly when that happened, so callers
        that care about freshness (e.g. the CLI's `rates` command) can say so
        instead of silently presenting a stale rate as current.
        """
        if base == quote:
            return RateLookup(rate=Decimal(1), rate_date=on_date, is_stale_fallback=False)

        cached = self._cached(base, quote, on_date)
        if cached is not None:
            return RateLookup(
                rate=Decimal(cached.rate), rate_date=cached.rate_date, is_stale_fallback=False
            )

        try:
            rate = self._provider.fetch_rate(base, quote, on_date)
        except ExchangeRateProviderError:
            fallback = self._most_recent_cached_on_or_before(base, quote, on_date)
            if fallback is not None:
                return RateLookup(
                    rate=Decimal(fallback.rate),
                    rate_date=fallback.rate_date,
                    is_stale_fallback=True,
                )
            raise ExchangeRateUnavailableError(
                f"No cached rate for {base}->{quote} on {on_date} and the "
                f"{self._provider.name} provider is unreachable."
            ) from None

        self._db.add(
            ExchangeRate(
                base_currency=base,
                quote_currency=quote,
                rate=rate,
                rate_date=on_date,
                source=self._provider.name,
            )
        )
        try:
            self._db.commit()
        except IntegrityError:
            # Another concurrent request cached this exact (base, quote, date)
            # in the gap between our cache-miss check and this insert (the
            # dashboard fires several portfolio requests in parallel on every
            # currency change). Their row is authoritative now; use it.
            self._db.rollback()
            cached = self._cached(base, quote, on_date)
            if cached is not None:
                return RateLookup(
                    rate=Decimal(cached.rate), rate_date=cached.rate_date, is_stale_fallback=False
                )
            raise
        return RateLookup(rate=rate, rate_date=on_date, is_stale_fallback=False)

    def get_rate(self, base: str, quote: str, on_date: dt.date) -> Decimal:
        """Convenience wrapper for callers that just want the number."""
        return self.get_rate_with_metadata(base, quote, on_date).rate

    def convert(
        self, amount: Decimal, from_currency: str, to_currency: str, on_date: dt.date
    ) -> Decimal:
        rate = self.get_rate(from_currency, to_currency, on_date)
        return amount * rate
