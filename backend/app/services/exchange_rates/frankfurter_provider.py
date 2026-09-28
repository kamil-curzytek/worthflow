from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import httpx

from app.net import ensure_system_trust_store
from app.services.exchange_rates.provider import ExchangeRateProvider, ExchangeRateProviderError

BASE_URL = "https://api.frankfurter.dev/v1"


class FrankfurterProvider(ExchangeRateProvider):
    """Free, no-API-key, ECB-backed rate provider with historical-date support."""

    name = "frankfurter"

    def __init__(
        self, timeout: float = 5.0, max_attempts: int = 3, retry_backoff: float = 0.5
    ) -> None:
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._retry_backoff = retry_backoff

    def fetch_rate(self, base: str, quote: str, on_date: dt.date) -> Decimal:
        if base == quote:
            return Decimal(1)

        ensure_system_trust_store()
        url = f"{BASE_URL}/{on_date.isoformat()}"

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = httpx.get(
                    url,
                    params={"from": base, "to": quote},
                    timeout=self._timeout,
                    follow_redirects=True,
                )
                response.raise_for_status()
                data = response.json()
                return Decimal(str(data["rates"][quote]))
            except (KeyError, ValueError) as exc:
                # Malformed/unexpected response shape — retrying won't help.
                raise ExchangeRateProviderError(
                    f"Unexpected response fetching {base}->{quote} for {on_date} "
                    f"from {self.name}: {exc}"
                ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    time.sleep(self._retry_backoff * attempt)

        raise ExchangeRateProviderError(
            f"Could not fetch {base}->{quote} rate for {on_date} from {self.name} "
            f"after {self._max_attempts} attempts: {last_error}"
        ) from last_error
