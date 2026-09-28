from fastapi import APIRouter

from app.domain.currencies.currency import SUPPORTED_CURRENCIES

router = APIRouter(prefix="/api/currencies", tags=["currencies"])


@router.get("")
def list_currencies():
    return {"currencies": sorted(SUPPORTED_CURRENCIES)}
