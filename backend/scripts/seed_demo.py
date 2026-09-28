"""Seeds data/demo/demo.db with entirely fictional accounts and history.

Run: .venv/Scripts/python.exe scripts/seed_demo.py

Point the app at the result with DATABASE_URL=sqlite:///./data/demo/demo.db
so the dashboard can be explored/demoed without touching real financial data.
The demo user's display name makes it obvious this isn't real data.
"""

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import models  # noqa: F401
from app.database.base import Base
from app.database.models import AccountType, AssetClass, SnapshotSource
from app.services import accounts_service, snapshots_service
from app.services.users_service import (
    LOCAL_USER_EMAIL,  # noqa: F401 (documents the real-user key we deliberately don't use)
    get_or_create_local_user,
)

DEMO_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "demo" / "demo.db"

ACCOUNTS = [
    ("Demo Checking", AccountType.CHECKING, AssetClass.CASH, "EUR", 2400, 15),
    ("Demo Savings", AccountType.SAVINGS, AssetClass.CASH, "EUR", 12000, 120),
    ("Demo Brokerage", AccountType.BROKERAGE, AssetClass.TRADING, "USD", 8000, 260),
    ("Demo Crypto Wallet", AccountType.CRYPTO, AssetClass.CRYPTO, "USD", 1500, -40),
]

MONTHS = 18


def month_range(n: int) -> list[dt.date]:
    today = dt.date.today().replace(day=1)
    dates = []
    for i in range(n, 0, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        dates.append(dt.date(year, month, 1))
    return dates


def synthetic_value(start: Decimal, monthly_drift: Decimal, month_index: int) -> Decimal:
    # Deterministic gentle upward walk with a bit of wave-like variation —
    # reproducible (no randomness) so re-running the script gives the same demo.
    import math

    wobble = Decimal(str(round(math.sin(month_index / 2.3) * float(monthly_drift) * 1.5, 2)))
    trend = monthly_drift * month_index
    value = start + trend + wobble
    return max(value, Decimal(0))


def main() -> None:
    DEMO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DEMO_DB_PATH.as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = get_or_create_local_user(db)
    # Override the display name so anyone poking at this DB directly sees it's fake.
    user.display_name = "Demo User"
    db.commit()

    months = month_range(MONTHS)

    for name, acct_type, asset_class, currency, start, drift in ACCOUNTS:
        account = accounts_service.get_or_create_account(
            db, user.id, name=name, type=acct_type, asset_class=asset_class, currency=currency
        )
        for i, month in enumerate(months):
            value = synthetic_value(Decimal(start), Decimal(drift), i)
            snapshots_service.add_or_update_monthly_snapshot(
                db,
                account=account,
                snapshot_date=month,
                value=value,
                source=SnapshotSource.MANUAL,
                note="demo data",
            )

    db.close()
    print(f"Seeded fictional demo data into {DEMO_DB_PATH}")
    print("Point DATABASE_URL at it to explore the app without real financial data:")
    print(f"  DATABASE_URL=sqlite:///{DEMO_DB_PATH.as_posix()}")


if __name__ == "__main__":
    main()
