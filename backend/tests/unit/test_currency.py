import pytest

from app.domain.currencies.currency import UnsupportedCurrencyError, validate_currency


def test_accepts_supported_currencies():
    assert validate_currency("EUR") == "EUR"
    assert validate_currency("usd") == "USD"
    assert validate_currency(" pln ") == "PLN"


def test_rejects_unsupported_currency():
    with pytest.raises(UnsupportedCurrencyError):
        validate_currency("GBP")
