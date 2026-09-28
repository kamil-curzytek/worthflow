"""Currency support.

Kept deliberately small: a fixed set of ISO 4217 codes the app understands for
display and conversion. Adding a currency later means adding it here, not
touching the storage layer (accounts/snapshots already store an arbitrary
3-letter currency code).
"""

SUPPORTED_CURRENCIES: set[str] = {"EUR", "USD", "PLN"}


class UnsupportedCurrencyError(ValueError):
    pass


def validate_currency(code: str) -> str:
    code = code.upper().strip()
    if code not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(
            f"Unsupported currency {code!r}. Supported: {sorted(SUPPORTED_CURRENCIES)}"
        )
    return code
