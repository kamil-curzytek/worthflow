"""Exchange-rate provider abstraction.

The app must not be hard-wired to one external FX API. Anything that can
answer "what was the rate from X to Y on date D" can be plugged in here.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from decimal import Decimal


class ExchangeRateProviderError(Exception):
    """Raised when a provider cannot answer (network down, API error, rate limit)."""


class ExchangeRateProvider(ABC):
    name: str

    @abstractmethod
    def fetch_rate(self, base: str, quote: str, on_date: dt.date) -> Decimal:
        """Return the base->quote rate for on_date. Raises ExchangeRateProviderError on failure."""
        raise NotImplementedError
