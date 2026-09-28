from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import accounts, currencies, imports, portfolio, snapshots, sub_ledger
from app.services.exchange_rates.service import ExchangeRateUnavailableError

app = FastAPI(
    title="Worthflow",
    description="Local-first personal savings and finance dashboard API.",
    version="0.1.0",
)

# Local-only dev frontend (Vite default). Not exposed beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(snapshots.router)
app.include_router(portfolio.router)
app.include_router(currencies.router)
app.include_router(imports.router)
app.include_router(sub_ledger.router)


@app.exception_handler(ExchangeRateUnavailableError)
def exchange_rate_unavailable_handler(request: Request, exc: ExchangeRateUnavailableError):
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Exchange rates are temporarily unavailable (no internet or the "
                f"rate provider is down): {exc}"
            )
        },
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}
