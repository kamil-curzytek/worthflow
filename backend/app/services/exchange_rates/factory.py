from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.exchange_rates.frankfurter_provider import FrankfurterProvider
from app.services.exchange_rates.provider import ExchangeRateProvider
from app.services.exchange_rates.service import ExchangeRateService

_PROVIDERS: dict[str, type[ExchangeRateProvider]] = {
    "frankfurter": FrankfurterProvider,
}


def build_exchange_rate_service(db: Session) -> ExchangeRateService:
    settings = get_settings()
    provider_cls = _PROVIDERS.get(settings.exchange_rate_provider)
    if provider_cls is None:
        raise ValueError(
            f"Unknown exchange rate provider {settings.exchange_rate_provider!r}. "
            f"Available: {sorted(_PROVIDERS)}"
        )
    return ExchangeRateService(db, provider_cls())
